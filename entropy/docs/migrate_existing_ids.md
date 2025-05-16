# Migrating Existing Customer and Supplier IDs

## WARNING: Critical Operation

> **DANGER:** This script (`entropy/utils/migrate_existing_ids.py`) performs **destructive database operations**. It renames the primary keys (`name` column) of existing Customer and Supplier documents.
>
> *   **BACKUP REQUIRED:** **ALWAYS** take a full database backup before running this script on any environment.
> *   **TEST THOROUGHLY:** Execute this script on a recent copy of your production data (a staging environment) **first**. Verify the results carefully.
> *   **EXCLUSIVE ACCESS:** Ensure no users are actively creating or modifying Customer or Supplier records while the migration is in progress to avoid conflicts.
> *   **IRREVERSIBLE (without backup):** Renaming primary keys is complex. Reversing the process without restoring a backup is extremely difficult and error-prone.

## Purpose

This script is designed to update the IDs (`name`) of existing `Customer` and `Supplier` records to match the new custom naming format implemented by `custom_naming.py` (`[NAME_PREFIX][COMPANY_ABBR][SEQ_NUM]`). This ensures consistency between newly created records and historical data.

## Prerequisites

1.  **`custom_naming.py`:** The helper functions (`get_name_prefix`, `get_company_abbr`, constants) from the finalized `custom_naming.py` script must be present and correctly imported by this migration script. The import path (`from entropy.utils.custom_naming import ...`) may need adjustment based on your app structure.
2.  **Database Backup:** A verified, restorable database backup is essential before proceeding.

## How it Works

The script is executed via the `bench execute` command and operates in batches for safety and scalability.

### 1. Command-Line Interface

The script uses `argparse` for configuration via command-line arguments passed within the `bench execute` call.

*   **`doctype` (Required):** Specifies whether to migrate `Customer` or `Supplier`.
*   **`--batch-size` (Optional):** Number of records processed per database transaction (default: 100). Smaller batches use less memory but might be slightly slower overall.
*   **`--dry-run` (Optional):** **Highly Recommended for testing.** Simulates the entire process, including ID generation and link checking, *without* modifying the database. Logs actions that *would* be taken.
*   **`--yes` / `-y` (Optional):** Skips the interactive confirmation prompt. **Use with extreme caution** only after thorough testing and backup verification.

### 2. Batch Processing

*   To handle potentially large numbers of Customers/Suppliers without overwhelming server memory, the script fetches records in batches (controlled by `--batch-size`).
*   It processes each batch, updates links, renames documents, and then commits the changes before fetching the next batch.

### 3. ID Generation (`generate_next_migration_id`)

*   **Migration-Specific Logic:** This function calculates the *next* available ID for an *existing* record during migration. It does **not** use the atomic counter (`_get_next_series_number_atomic`) from `custom_naming.py`, as that's designed for *new* concurrent creations.
*   **Finding Max Existing:** For a given `name_prefix` and `company_abbr` combination (e.g., "SPAABC"):
    *   It queries the database for the highest existing ID that matches the pattern `PREFIX+ABBR+NUMBERS` (e.g., `SPAABC123`). It uses `LIKE` and `REGEXP` for accuracy.
    *   It caches the highest number found for each prefix within the script's run to avoid repeated database queries.
    *   It increments the highest found number to get the next sequence number for the migration.
    *   If no existing formatted ID is found for that prefix, it starts the sequence at 1.
*   **Generates ID:** Constructs the new ID using the prefix, abbreviation, and the determined sequence number, applying the correct padding.

### 4. Format Check

*   Before attempting to generate a new ID, the script checks if the `old_name` already conforms to the expected `PREFIX+ABBR+SEQUENCENUMBER` format.
*   If it does, the record is skipped to avoid unnecessary processing and potential errors.

### 5. Link Updating (`update_links_for_document`)

*   **Critical Step:** This is arguably the most complex part of renaming. Before `frappe.rename_doc` is called, this function finds all references to the `old_name` across the *entire database* and updates them to the `new_name`.
*   **Comprehensive Check:** It handles:
    *   Standard `Link` fields (in standard DocTypes and Custom Fields).
    *   `Dynamic Link` fields (checking both the field holding the doctype name and the field holding the document name).
*   **Error Handling:** Logs errors if updating links in a specific table fails but continues the overall process.

### 6. Renaming (`frappe.rename_doc`)

*   After links are updated (or identified in dry run), this function performs the actual rename of the document's primary key (`name`) in its table (`tabCustomer` or `tabSupplier`).
*   Uses `force=True` and `ignore_permissions=True` which are often necessary for admin-run migrations but require caution.

### 7. Error Handling & Commits

*   **Individual Record Failures:** If updating links or renaming fails for a *single record*, the error is logged, the `failed_count` is incremented, and the script proceeds to the next record in the batch. This prevents one bad record from halting the entire migration.
*   **Batch Commits:** Database changes are committed periodically after each batch. This saves progress but means a failure mid-batch won't roll back previously committed batches.
*   **Critical Failures:** If a rename fails *after* links were updated (in a live run), a critical log message is generated, as manual intervention might be needed for that specific record. A final `try...except` block attempts to roll back the *current* transaction if a catastrophic error occurs.

### 8. Dry Run Mode (`--dry-run`)

*   Simulates ID generation.
*   Logs which links *would* be updated.
*   Logs which documents *would* be renamed.
*   **Does not execute `frappe.db.sql("UPDATE ...")` or `frappe.rename_doc(...)`.**
*   Essential for verifying the script's logic and identifying potential issues before modifying live data.

## Execution Steps

1.  **BACKUP YOUR DATABASE.** Verify the backup is complete and restorable.
2.  **Test on Staging (Dry Run):**
    ```bash
    bench --site your-staging-site execute entropy.utils.migrate_existing_ids.run_migration --args='{"doctype":"Customer", "dry_run":true}'
    bench --site your-staging-site execute entropy.utils.migrate_existing_ids.run_migration --args='{"doctype":"Supplier", "dry_run":true}'
    ```
    *   Review `logs/migration.log` carefully for generated IDs, skipped records, potential link updates, and any errors.
3.  **Test on Staging (Live Run):** If the dry run looks good, perform a live run on staging:
    ```bash
    bench --site your-staging-site execute entropy.utils.migrate_existing_ids.run_migration --args='{"doctype":"Customer"}' # Will prompt for confirmation
    bench --site your-staging-site execute entropy.utils.migrate_existing_ids.run_migration --args='{"doctype":"Supplier"}' # Will prompt for confirmation
    ```
    *   Thoroughly check sample Customer/Supplier records in the UI. Verify their new IDs. Check documents that link to them (e.g., Sales Orders, Purchase Orders, Journal Entries) to ensure the links were updated correctly.
4.  **Schedule Production Run:** Plan a maintenance window when user activity is minimal.
5.  **Execute on Production (Live Run):**
    ```bash
    # Ensure you are targeting the correct site!
    bench --site your-production-site execute entropy.utils.migrate_existing_ids.run_migration --args='{"doctype":"Customer"}' # Will prompt
    bench --site your-production-site execute entropy.utils.migrate_existing_ids.run_migration --args='{"doctype":"Supplier"}' # Will prompt
    # OR, if you are absolutely certain after testing (use with caution):
    # bench --site your-production-site execute entropy.utils.migrate_existing_ids.run_migration --args='{"doctype":"Customer", "yes":true}'
    ```
6.  **Monitor:** Closely monitor the console output and `logs/migration.log` during execution.
7.  **Verify:** After completion, perform spot checks on production data similar to the staging verification.

## Logging

The script uses a dedicated Frappe logger named `migration`. Check the `logs/migration.log` file for detailed information about batches, skipped records, generated IDs, successful renames, link updates, and any errors encountered.

## Recovery

*   **Minor Errors:** If only a few records fail, note the `old_name` from the logs. Manual correction might be possible (e.g., manually renaming and checking links).
*   **Major Errors:** If significant issues occur, the safest approach is typically to **restore the database backup** taken before the migration attempt.