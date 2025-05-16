import frappe
import re
import argparse
import sys
from frappe.utils import cstr, cint
from frappe.exceptions import DoesNotExistError

# Import the *correct* naming helpers from your finalized custom_naming script
# Make sure the path is correct for your app structure
try:
    # Adjust the import path based on your app name ('entropy') and file location
    from entropy.utils.custom_naming import get_name_prefix, get_company_abbr, DEFAULT_PADDING, MAX_PREFIX_LENGTH 
except ImportError:
    print("ERROR: Could not import naming helpers from entropy.utils.custom_naming.")
    print("Ensure the file exists and the path is correct.")
    sys.exit(1)

# Setup Logger
logger = frappe.logger("migration", allow_site=True, file_count=50)

# --- Configuration ---
DEFAULT_BATCH_SIZE = 100

# --- Helper Functions ---

def get_link_fields(doctype):
    """Gets standard Link and Dynamic Link fields pointing to a given doctype."""
    link_fields = []

    # Standard Link Fields
    std_links = frappe.get_all("DocField",
                              fields=["parent", "fieldname"],
                              filters={"fieldtype": "Link", "options": doctype})
    link_fields.extend(std_links)

    # Custom Link Fields
    custom_links = frappe.get_all("Custom Field",
                                 fields=["dt as parent", "fieldname"],
                                 filters={"fieldtype": "Link", "options": doctype})
    link_fields.extend(custom_links)

    # Dynamic Link Fields (fetch all and filter in code)
    # We need the options field which stores the fieldname holding the target doctype
    dynamic_link_meta = frappe.get_all("DocField",
                                      fields=["parent", "fieldname", "options"],
                                      filters={"fieldtype": "Dynamic Link"})
    custom_dynamic_link_meta = frappe.get_all("Custom Field",
                                        fields=["dt as parent", "fieldname", "options"],
                                        filters={"fieldtype": "Dynamic Link"})

    dynamic_link_meta.extend(custom_dynamic_link_meta)

    return link_fields, dynamic_link_meta


def update_links_for_document(doctype, old_name, new_name, link_fields, dynamic_link_meta, dry_run=False):
    """
    Updates standard Link and Dynamic Link fields referencing the renamed document.
    """
    logger.info(f"Updating links for {doctype}: {old_name} -> {new_name}")

    # 1. Update Standard Link Fields
    for field in link_fields:
        parent_doctype = field.parent
        field_name = field.fieldname
        # Skip self-references if any exist in DocField definitions
        if parent_doctype == doctype and field_name == "name": 
            continue
        try:
            logger.debug(f"Checking links in {parent_doctype}.{field_name}")
            update_query = f"""
                UPDATE `tab{parent_doctype}`
                SET `{field_name}` = %(new_name)s
                WHERE `{field_name}` = %(old_name)s
            """
            if not dry_run:
                frappe.db.sql(update_query, {"new_name": new_name, "old_name": old_name})
            else:
                # In dry run, we might check if any records *would* be updated
                check_query = f"""
                    SELECT COUNT(*) 
                    FROM `tab{parent_doctype}` 
                    WHERE `{field_name}` = %(old_name)s
                """
                count = frappe.db.sql(check_query, {"old_name": old_name})
                if count and count[0][0] > 0:
                    logger.info(f"[Dry Run] Would update {count[0][0]} links in {parent_doctype}.{field_name}")

        except Exception as e:
            # Log specific table/field errors but continue
            logger.error(f"Error updating links in `tab{parent_doctype}`.{field_name} for {old_name}: {e}", exc_info=True)


    # 2. Update Dynamic Link Fields
    for meta in dynamic_link_meta:
        parent_doctype = meta.parent
        dyn_link_fieldname = meta.fieldname # Field storing the name (e.g., 'link_name')
        options_fieldname = meta.options # Field storing the doctype (e.g., 'link_doctype')

        # Skip self-references
        if parent_doctype == doctype:
             continue
             
        try:
            logger.debug(f"Checking dynamic links in {parent_doctype} (link field: {dyn_link_fieldname}, type field: {options_fieldname})")
            # Query where the type matches our doctype AND the name matches the old_name
            update_query = f"""
                UPDATE `tab{parent_doctype}`
                SET `{dyn_link_fieldname}` = %(new_name)s
                WHERE `{options_fieldname}` = %(target_doctype)s
                  AND `{dyn_link_fieldname}` = %(old_name)s
            """
            if not dry_run:
                frappe.db.sql(update_query, {
                    "new_name": new_name,
                    "target_doctype": doctype,
                    "old_name": old_name
                })
            else:
                 check_query = f"""
                    SELECT COUNT(*) 
                    FROM `tab{parent_doctype}` 
                    WHERE `{options_fieldname}` = %(target_doctype)s
                      AND `{dyn_link_fieldname}` = %(old_name)s
                 """
                 count = frappe.db.sql(check_query, {"target_doctype": doctype, "old_name": old_name})
                 if count and count[0][0] > 0:
                    logger.info(f"[Dry Run] Would update {count[0][0]} dynamic links in {parent_doctype}.{dyn_link_fieldname}")

        except Exception as e:
            logger.error(f"Error updating dynamic links in `tab{parent_doctype}` for {old_name} (field: {dyn_link_fieldname}): {e}", exc_info=True)


def generate_next_migration_id(doctype, name_field_value, company, existing_sequences):
    """
    Generates the next available ID for migration purposes.
    Finds the highest existing sequence number for the name/company prefix
    and increments it. Stores found max sequences in `existing_sequences` dict.

    Args:
        doctype (str): 'Customer' or 'Supplier'.
        name_field_value (str): The value from customer_name or supplier_name.
        company (str): The company associated with the record.
        existing_sequences (dict): Cache to store max sequence found per prefix.

    Returns:
        str: The newly generated ID in the format PREFIX+COMPANY_ABBR+SEQ.
             Returns None if prefix/abbr cannot be generated.
    """
    if not name_field_value:
        logger.warning(f"Skipping ID generation: Name field is empty for a {doctype} record.")
        return None

    name_prefix = get_name_prefix(name_field_value)
    company_abbr = get_company_abbr(company)
    combined_prefix = f"{name_prefix}{company_abbr}"

    # Check cache first
    if combined_prefix in existing_sequences:
        next_number = existing_sequences[combined_prefix] + 1
    else:
        # Query database for the highest existing ID with this prefix
        # This needs to find IDs like "SPAABC001", "SPAABC123", etc.
        query = f"""
            SELECT name
            FROM `tab{doctype}`
            WHERE name LIKE %(like_pattern)s
              AND name REGEXP %(regex_pattern)s -- Ensure it ends with numbers
            ORDER BY name DESC
            LIMIT 1
        """
        like_pattern = combined_prefix + "%"
        # Regex to match the prefix followed ONLY by digits until the end
        regex_pattern = f"^{re.escape(combined_prefix)}(\\d+)$" 
        
        try:
            last_id_result = frappe.db.sql(query, {"like_pattern": like_pattern, "regex_pattern": regex_pattern})
            
            if last_id_result:
                last_name = last_id_result[0][0]
                match = re.search(regex_pattern, last_name)
                if match:
                    last_number = cint(match.group(1))
                    next_number = last_number + 1
                    logger.debug(f"Found existing max for {combined_prefix}: {last_name} (Num: {last_number}). Next is {next_number}.")
                else:
                    # Should not happen if regex in query worked, but handle defensively
                    logger.warning(f"Regex mismatch for {last_name} with pattern {regex_pattern}. Starting sequence at 1 for {combined_prefix}.")
                    next_number = 1
            else:
                # No existing IDs found with this prefix and numeric ending
                logger.debug(f"No existing numeric IDs found for prefix {combined_prefix}. Starting sequence at 1.")
                next_number = 1
                
        except Exception as e:
            logger.error(f"Error querying max ID for {combined_prefix} in {doctype}: {e}", exc_info=True)
            # Cannot safely generate ID if query fails
            return None

    # Update cache and generate new ID
    existing_sequences[combined_prefix] = next_number
    new_id = f"{combined_prefix}{cstr(next_number).zfill(DEFAULT_PADDING)}"
    return new_id


# --- Main Migration Logic ---

def migrate_doctype(doctype, name_field, company_field, batch_size=DEFAULT_BATCH_SIZE, dry_run=False):
    """
    Performs the ID migration for the specified doctype in batches.
    """
    logger.info(f"{'DRY RUN: ' if dry_run else ''}Starting migration for DocType: {doctype}")

    # --- Initialization ---
    processed_count = 0
    renamed_count = 0
    skipped_count = 0
    failed_count = 0
    start = 0
    existing_sequences = {} # Cache for max sequence numbers found { "PREFIXABBR": max_num }

    # Pre-fetch link field definitions once
    link_fields, dynamic_link_meta = get_link_fields(doctype)
    logger.info(f"Found {len(link_fields)} standard link fields and {len(dynamic_link_meta)} dynamic link field definitions to check.")

    # --- Batch Processing Loop ---
    while True:
        logger.info(f"Processing batch starting from record: {start}")
        try:
            # Fetch a batch of documents
            records = frappe.get_list(
                doctype,
                fields=["name", name_field, company_field],
                limit_start=start,
                limit_page_length=batch_size,
                order_by="name asc" # Process in a consistent order
            )
        except Exception as e:
             logger.error(f"FATAL: Could not fetch batch for {doctype} starting at {start}. Aborting. Error: {e}", exc_info=True)
             break # Exit the loop on fetch failure

        if not records:
            logger.info(f"No more records found for {doctype}.")
            break # Exit loop if no more records

        # --- Process Records in Batch ---
        for record in records:
            processed_count += 1
            old_name = record.name
            name_value = record.get(name_field)
            company_value = record.get(company_field)

            # --- Check if already in correct format ---
            try:
                current_name_prefix = get_name_prefix(name_value)
                current_company_abbr = get_company_abbr(company_value)
                # Pattern: Prefix + CompanyAbbr + Padding digits (or more)
                correct_format_pattern = f"^{re.escape(current_name_prefix)}{re.escape(current_company_abbr)}\\d{{{DEFAULT_PADDING},}}$"

                if re.match(correct_format_pattern, old_name):
                    logger.debug(f"Skipping {old_name} - already in correct format.")
                    skipped_count += 1
                    continue # Move to the next record in the batch
            except Exception as e:
                logger.warning(f"Error checking format for {old_name} (Name: {name_value}, Company: {company_value}): {e}. Skipping.")
                skipped_count +=1
                continue


            # --- Generate New ID ---
            try:
                 new_name = generate_next_migration_id(doctype, name_value, company_value, existing_sequences)
                 if not new_name:
                     logger.error(f"Failed to generate new ID for {old_name} (Name: {name_value}, Company: {company_value}). Skipping.")
                     failed_count += 1
                     continue
                 
                 # Prevent accidental renaming to the same name (should be caught by format check, but belt-and-suspenders)
                 if new_name == old_name:
                     logger.warning(f"Generated new name {new_name} is identical to old name {old_name}. Skipping.")
                     skipped_count += 1
                     continue
                     
            except Exception as e:
                logger.error(f"Critical error during new ID generation for {old_name}: {e}", exc_info=True)
                failed_count += 1
                continue # Skip this record


            # --- Perform Rename (within try...except for this record) ---
            try:
                logger.info(f"Attempting rename: {old_name} -> {new_name}")

                # ** Crucial Step 1: Update Links **
                update_links_for_document(doctype, old_name, new_name, link_fields, dynamic_link_meta, dry_run)

                # ** Crucial Step 2: Rename Document **
                if not dry_run:
                    # Use force=True cautiously, ensures rename happens even if hooks fail, but link updates are vital
                    # Setting ignore_permissions=True is often needed for migrations run by Admin
                    frappe.rename_doc(doctype, old_name, new_name, force=True, ignore_permissions=True) 
                    logger.info(f"Successfully renamed: {old_name} -> {new_name}")
                else:
                    logger.info(f"[Dry Run] Would rename {doctype}: {old_name} -> {new_name}")

                renamed_count += 1

            except Exception as e:
                logger.error(f"FAILED to rename {doctype}: {old_name} -> {new_name}. Error: {e}", exc_info=True)
                failed_count += 1
                # IMPORTANT: If rename_doc fails after links were updated (in non-dry-run),
                # manual intervention might be needed for this record.
                # The database transaction *should* handle this if run via `bench execute`,
                # but logging the failure clearly is vital.
                if not dry_run:
                     logger.critical(f"Potential data inconsistency for {old_name}. Links might point to {new_name}, but rename failed.")
                     # We do NOT rollback the whole batch here, just log the individual failure.
                     # Periodic commits ensure prior successes are saved.

            # --- Periodic Commit (outside individual record try/except) ---
            if processed_count % batch_size == 0:
                 if not dry_run:
                    logger.info(f"Committing changes after {processed_count} records...")
                    frappe.db.commit()
                    logger.info("Commit successful.")
                 else:
                    logger.info(f"[Dry Run] Would commit after {processed_count} records.")


        # --- End of Batch ---
        start += batch_size # Move to the next batch

    # --- Final Commit ---
    if not dry_run:
        logger.info("Committing final batch changes...")
        frappe.db.commit()
        logger.info("Final commit successful.")
    else:
         logger.info("[Dry Run] Final commit would happen here.")

    # --- Summary ---
    logger.info("\n--- Migration Summary ---")
    logger.info(f"DocType: {doctype}")
    logger.info(f"Total records processed: {processed_count}")
    logger.info(f"Successfully renamed: {renamed_count}")
    logger.info(f"Skipped (already correct format / other): {skipped_count}")
    logger.info(f"Failed: {failed_count}")
    logger.info("-------------------------\n")

    return failed_count == 0 # Return True if successful, False otherwise

# --- Script Execution ---

def run_migration(args):
    """Sets up flags and runs the migration for the specified doctype."""

    if not args.yes and not args.dry_run:
        print("\n" + "="*50)
        print("WARNING: This script will RENAME document IDs (primary keys).")
        print("This is a potentially destructive operation.")
        print("1. TAKE A DATABASE BACKUP before proceeding.")
        print("2. TEST THOROUGHLY on a staging environment first.")
        print("3. Ensure no users are actively creating/modifying these records during migration.")
        print("="*50 + "\n")
        confirm = input(f"Type 'YES' to confirm you have taken a backup and want to proceed for doctype '{args.doctype}': ")
        if confirm != "YES":
            print("Migration aborted by user.")
            return

    # Set flags often needed for migrations
    frappe.flags.in_migrate = True
    frappe.flags.in_install = True # Helps bypass certain hooks/validations
    #frappe.db.auto_commit_on_many_writes = True # Use explicit commits instead

    success = False
    try:
        if args.doctype == "Customer":
            success = migrate_doctype("Customer", "customer_name", "company", args.batch_size, args.dry_run)
        elif args.doctype == "Supplier":
            success = migrate_doctype("Supplier", "supplier_name", "company", args.batch_size, args.dry_run)
        else:
            logger.error(f"Unsupported doctype specified: {args.doctype}")
            print(f"ERROR: Unsupported doctype: {args.doctype}. Choose 'Customer' or 'Supplier'.")

    except Exception as e:
        logger.error(f"Unhandled exception during migration: {e}", exc_info=True)
        print(f"FATAL ERROR during migration: {e}")
        frappe.db.rollback() # Rollback any uncommitted changes
        print("Rolled back current transaction.")
    finally:
        # Unset flags
        frappe.flags.in_migrate = False
        frappe.flags.in_install = False
        #frappe.db.auto_commit_on_many_writes = False

        if success:
             logger.info("Migration process completed successfully.")
             print("Migration process completed successfully.")
        else:
             logger.warning("Migration process completed with failures. Check logs.")
             print("WARNING: Migration process completed with failures. Please check migration.log.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate Customer/Supplier IDs to new format (PREFIX+COMPANY+SEQ).")
    parser.add_argument("doctype", choices=["Customer", "Supplier"], help="Specify the DocType to migrate (Customer or Supplier).")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help=f"Number of records to process per batch (default: {DEFAULT_BATCH_SIZE}).")
    parser.add_argument("--dry-run", action="store_true", help="Simulate the migration without making any database changes.")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip the confirmation prompt (USE WITH CAUTION!).")

    args = parser.parse_args()

    # Ensure we are in a Frappe context
    if not frappe.db:
        print("ERROR: This script must be run using 'bench execute'.")
        print("Example: bench execute entropy.utils.migrate_existing_ids.run_migration --args='{\"doctype\":\"Customer\", \"dry_run\":true}'")
        # Or using argparse directly if bench execute passes argv correctly (might need testing)
        # print("Example: bench execute entropy.utils.migrate_existing_ids --doctype Customer --dry-run") 
        sys.exit(1)
        
    run_migration(args)
