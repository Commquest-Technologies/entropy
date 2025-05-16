import frappe
from frappe.model.document import Document
import re
from frappe.utils import cstr, cint 
from frappe.exceptions import DuplicateEntryError, ValidationError

# --- Constants ---
DEFAULT_COMPANY_ABBR = "CO"
DEFAULT_NAME_PREFIX = "UNK"
DEFAULT_PADDING = 3
MAX_PREFIX_LENGTH = 3
# The value we store in the `doctype` column of `tabSingles` to identify our series group
SERIES_DOCTYPE_KEY = "CustomNameSeries" # Can be kept, but clarifies it's not a real DocType name
# The value we store in the `field` column of `tabSingles` to identify the counter value
# This name itself doesn't matter much, as long as it's consistent.
SERIES_FIELDNAME_KEY = "current_value"

# Get a logger instance
logger = frappe.logger("custom_naming", allow_site=True)

def get_company_abbr(company=None):
    """
    Gets the abbreviation of the company.

    If no company is provided, it attempts to fetch the default company
    for the current user. If no default is found, uses DEFAULT_COMPANY_ABBR.

    Caches the result for performance.

    Args:
        company (str, optional): The name of the Company DocType. Defaults to None.

    Returns:
        str: The company abbreviation (e.g., "ABC") or the default ("CO").
    """
    if not company:
        company = frappe.defaults.get_user_default("company")
        logger.debug(f"No company provided or found on doc, using user default: {company}")

    if not company:
        logger.warning("No company found (user default or provided), using default abbreviation.")
        return DEFAULT_COMPANY_ABBR

    try:
        # Use get_cached_value for efficiency
        company_abbr = frappe.get_cached_value("Company", company, "abbr")
        if not company_abbr:
            logger.warning(f"Company '{company}' found, but abbreviation is empty. Using default.")
            return DEFAULT_COMPANY_ABBR

        logger.debug(f"Fetched abbreviation '{company_abbr}' for company '{company}'.")
        return company_abbr
    except Exception as e:
        # Log specific error if company lookup fails
        logger.error(f"Error fetching abbreviation for company '{company}': {str(e)}", exc_info=True)
        return DEFAULT_COMPANY_ABBR

def get_name_prefix(name_field, max_length=MAX_PREFIX_LENGTH):
    """
    Extracts a clean, uppercase, alphanumeric prefix from a name string.

    Handles empty or non-alphanumeric names by returning DEFAULT_NAME_PREFIX.

    Args:
        name_field (str): The input name (e.g., Customer Name, Supplier Name).
        max_length (int): The maximum length of the prefix.

    Returns:
        str: The generated prefix (e.g., "SPA") or the default ("UNK").
    """
    if not name_field:
        logger.debug("Name field is empty, returning default prefix.")
        return DEFAULT_NAME_PREFIX

    logger.debug(f"Generating prefix for: '{name_field}'")

    # Remove non-alphanumeric characters
    cleaned_name = re.sub(r'[^a-zA-Z0-9]', '', cstr(name_field))

    if not cleaned_name:
        # If cleaning resulted in an empty string (e.g., name was "---")
        logger.debug("Name field contains no alphanumeric characters, returning default prefix.")
        return DEFAULT_NAME_PREFIX

    # Take the first `max_length` characters and convert to uppercase
    prefix = cleaned_name[:max_length].upper()

    logger.debug(f"Generated prefix: '{prefix}'")
    return prefix

def _get_next_series_number_atomic(series_key, padding=DEFAULT_PADDING, initial_value=1):
    """
    Atomically retrieves and increments the next number for a given series key.

    Uses the `tabSingles` table and database row locking (`FOR UPDATE`) to prevent
    race conditions when multiple documents are saved concurrently. This is crucial
    for ensuring unique IDs under load.

    The `tabSingles` table is a key-value store in Frappe. We use:
    - `doctype` column: To store our unique series identifier (e.g., "CUSTSPAABC").
                       We use the constant `SERIES_DOCTYPE_KEY` conceptually, but
                       pass the specific generated key like "CUSTSPAABC".
    - `field` column: To store a fixed identifier for the counter value within that series.
                      We use the constant `SERIES_FIELDNAME_KEY` (e.g., "current_value").
    - `value` column: To store the actual last used number for the series.

    Args:
        series_key (str): A unique key identifying the series (e.g., "CUSTSPAABC"). This
                          will be stored in the `doctype` column of `tabSingles`.
        padding (int): The number of digits for zero-padding (e.g., 3 -> 001).
        initial_value (int): The starting number if the series doesn't exist yet.

    Returns:
        str: The next sequence number, zero-padded (e.g., "001", "042").

    Raises:
        Exception: Propagates database errors if the atomic update fails unexpectedly.
                   Also throws Frappe exception if initialization fails after concurrency detection.

    Corrections Applied:
        - Uses correct column name 'field' instead of 'fieldname'.
        - Removed references to non-existent 'modified' column.
    """
    logger.debug(f"Getting next atomic series number for key: '{series_key}' using field: '{SERIES_FIELDNAME_KEY}'")

    # --- Step 1: Try to select the existing value, locking the row ---
    # The FOR UPDATE clause is essential for atomicity. It prevents other transactions
    # from reading or writing this specific row until the current transaction completes.
    # This query targets the specific row identified by our series_key (in doctype column)
    # and our fixed field identifier (in field column).
    current_val = frappe.db.sql(f"""
        SELECT `value`
        FROM `tabSingles`
        WHERE `doctype`=%s AND `field`=%s
        FOR UPDATE
    """, (series_key, SERIES_FIELDNAME_KEY))

    # --- Step 2: Handle if the series doesn't exist yet ---
    if not current_val:
        logger.debug(f"Series key '{series_key}' / field '{SERIES_FIELDNAME_KEY}' not found. Initializing.")
        try:
            # Insert the first record for this series.
            # Note: No 'modified' column included here.
            frappe.db.sql("""
                INSERT INTO `tabSingles` (`doctype`, `field`, `value`)
                VALUES (%s, %s, %s)
            """, (series_key, SERIES_FIELDNAME_KEY, str(initial_value)))
            next_number = initial_value
            logger.debug(f"Initialized series '{series_key}' / field '{SERIES_FIELDNAME_KEY}' to {initial_value}.")

        # --- Step 2a: Handle rare race condition during insertion ---
        except DuplicateEntryError:
            # This can happen if two processes check (`SELECT FOR UPDATE`), both find nothing,
            # and then both try to `INSERT` almost simultaneously. One succeeds, the other gets this error.
            # The `FOR UPDATE` lock makes this *very* unlikely, but we handle it defensively.
            logger.warning(f"Concurrent creation detected for series '{series_key}' / field '{SERIES_FIELDNAME_KEY}'. Re-fetching with lock.")
            # Re-query *with the lock* to get the value inserted by the other process.
            current_val = frappe.db.sql(f"""
                SELECT `value`
                FROM `tabSingles`
                WHERE `doctype`=%s AND `field`=%s
                FOR UPDATE
            """, (series_key, SERIES_FIELDNAME_KEY))

            # If it's *still* not found after a DuplicateEntryError, something is deeply wrong.
            if not current_val:
                 logger.error(f"CRITICAL: Failed to retrieve series counter for '{series_key}' / '{SERIES_FIELDNAME_KEY}' even after DuplicateEntryError.")
                 frappe.throw(f"Failed to initialize or retrieve series counter for '{series_key}' / '{SERIES_FIELDNAME_KEY}' after concurrency issue.")

            # If re-fetch succeeded, proceed to increment the value found.
            last_number = cint(current_val[0][0])
            next_number = last_number + 1
            logger.debug(f"After concurrent creation, fetched last_number: {last_number}, calculating next: {next_number}")
            # Update the value (incrementing what the other process inserted).
            # Note: No 'modified' column included here.
            frappe.db.sql("""
                UPDATE `tabSingles`
                SET `value`=%s
                WHERE `doctype`=%s AND `field`=%s
            """, (str(next_number), series_key, SERIES_FIELDNAME_KEY))
            logger.debug(f"Updated series '{series_key}' / field '{SERIES_FIELDNAME_KEY}' to {next_number} after handling concurrency.")

    # --- Step 3: Handle if the series already exists ---
    else:
        # The `SELECT FOR UPDATE` was successful and returned the current value.
        last_number = cint(current_val[0][0])
        next_number = last_number + 1
        logger.debug(f"Series key '{series_key}' / field '{SERIES_FIELDNAME_KEY}' found. Last value: {last_number}, Next value: {next_number}")
        # Update the row (which is still locked by `FOR UPDATE`) with the incremented value.
        # Note: No 'modified' column included here.
        frappe.db.sql("""
            UPDATE `tabSingles`
            SET `value`=%s
            WHERE `doctype`=%s AND `field`=%s
        """, (str(next_number), series_key, SERIES_FIELDNAME_KEY))
        logger.debug(f"Updated series '{series_key}' / field '{SERIES_FIELDNAME_KEY}' to {next_number}.")


    # --- Step 4: Format and return the result ---
    # The transaction will commit automatically upon successful completion of the
    # calling method (e.g., `autoname`), releasing the lock. If an error occurs
    # before commit, the transaction rolls back, undoing the INSERT/UPDATE.
    formatted_number = cstr(next_number).zfill(padding)
    logger.debug(f"Returning formatted number: '{formatted_number}' for key '{series_key}' / field '{SERIES_FIELDNAME_KEY}'")
    return formatted_number

class CustomCustomer(Document):
    """
    Custom Customer DocType class with enhanced naming and duplicate prevention.

    Overrides `autoname` to generate IDs based on Customer Name prefix,
    Company Abbreviation, and an atomic counter.
    Overrides `validate` to prevent duplicate Customer Names (case-insensitive).
    """

    def autoname(self):
        """
        Sets the document `name` (ID) automatically using the format:
        [CUSTOMER_NAME_PREFIX][COMPANY_ABBR][ATOMIC_SEQ_NUM]
        Example: CUSABC001

        Relies on the user's default company if no company context is directly
        available on the Customer document during autonaming (as Customer DocType
        doesn't have a direct 'company' link field).

        Raises:
            frappe.ValidationError: If Customer Name is missing.
        """
        if not self.customer_name:
            # Ensure the primary input for the name is present
            raise ValidationError(frappe._("Customer Name is required to generate the ID."))

        # Safely get the company value from the document, if available.
        # This will often be None for Customer, as it doesn't have a direct 'company' field.
        company_from_doc = self.get("company")
        logger.debug(f"Autonaming Customer: '{self.customer_name}', Company from Doc (if any): '{company_from_doc}'")

        # 1. Get Company Abbreviation
        # get_company_abbr gracefully handles None by checking user defaults.
        company_abbr = get_company_abbr(company_from_doc)

        # 2. Get Name Prefix
        # Extracts prefix like 'SPA' from 'Spar'.
        name_prefix = get_name_prefix(self.customer_name)

        # 3. Construct the unique series key for the atomic counter
        # This key combines identifying information to ensure separate sequences
        # for different name prefixes and companies.
        # Example: 'CUST' + 'SPA' + 'ABC' -> "CUSTSPAABC"
        series_key = f"CUST{name_prefix}{company_abbr}"

        # 4. Get the next sequence number atomically using the helper function
        try:
            # This function handles the complexities of atomic incrementing via tabSingles
            sequence_number = _get_next_series_number_atomic(series_key, padding=DEFAULT_PADDING)
        except Exception as e:
             # Catch potential errors from the atomic counter function
             logger.error(f"Failed to get next series number for key '{series_key}': {str(e)}", exc_info=True)
             # Provide clear feedback to the user
             frappe.throw(
                 frappe._("Failed to generate the next ID number. Please check the logs or try again. Error: {0}").format(str(e)),
                 title="ID Generation Failed"
             )
             return # Exit autoname if ID generation fails

        # 5. Combine parts to form the final document name (ID)
        self.name = f"{name_prefix}{company_abbr}{sequence_number}"
        logger.info(f"Generated Customer ID: {self.name} for Customer Name: '{self.customer_name}', using Company Abbr: '{company_abbr}'")

    def validate(self):
        """
        Validates the Customer document before saving.

        Ensures Customer Name is provided.
        Prevents saving if another Customer exists with the same Customer Name
        (case-insensitive comparison, ignoring leading/trailing whitespace).
        """
        if not self.customer_name:
            # Validation consistency: Customer Name is mandatory.
            raise ValidationError(frappe._("Customer Name cannot be empty."))

        # Prepare the name for case-insensitive and whitespace-insensitive comparison
        normalized_customer_name = cstr(self.customer_name).strip().lower()

        # Placeholder for the current document's name. If it's a new document ('__islocal'),
        # self.name might not be set yet. Using a highly unlikely placeholder avoids
        # matching against NULL or an empty string in the DB query.
        current_name = self.name if not self.is_new() else "@@@NEW_DOC_PLACEHOLDER@@@"

        # Query for existing customers with the same normalized name, *excluding* the current document.
        # The `name != %(current_name)s` is crucial to allow saving updates to an existing customer
        # without triggering the duplicate check against itself.
        existing = frappe.db.sql("""
            SELECT name, customer_name
            FROM `tabCustomer`
            WHERE LOWER(TRIM(customer_name)) = %(normalized_name)s
            AND name != %(current_name)s
            LIMIT 1
        """, {
            "normalized_name": normalized_customer_name,
            "current_name": current_name
        }, as_dict=True)

        # If the query returned a result, a duplicate exists.
        if existing:
            existing_doc = existing[0]
            logger.warning(f"Validation failed: Duplicate customer name '{self.customer_name}' found. Existing record: {existing_doc.name}")
            # Throw a specific DuplicateEntryError for better error handling/reporting.
            # Provide clear, translatable feedback to the user.
            frappe.throw(
                frappe._("A Customer with the name '{0}' already exists: {1}").format(
                    existing_doc.customer_name, frappe.bold(existing_doc.name)
                ),
                exc=DuplicateEntryError, # Specify the exception type
                title="Duplicate Name"
            )
        logger.debug(f"Customer validation passed for: {self.name or '(New Document)'}")


class CustomSupplier(Document):
    """
    Custom Supplier DocType class with enhanced naming and duplicate prevention.

    Overrides `autoname` to generate IDs based on Supplier Name prefix,
    Company Abbreviation, and an atomic counter.
    Overrides `validate` to prevent duplicate Supplier Names (case-insensitive).
    """

    def autoname(self):
        """
        Sets the document `name` (ID) automatically using the format:
        [SUPPLIER_NAME_PREFIX][COMPANY_ABBR][ATOMIC_SEQ_NUM]
        Example: SUPSPAABC001

        Relies on the user's default company if no company context is directly
        available on the Supplier document during autonaming. Uses `self.get`
        for safe access, although Supplier often *does* have a company field.

        Raises:
            frappe.ValidationError: If Supplier Name is missing.
        """
        if not self.supplier_name:
            raise ValidationError(frappe._("Supplier Name is required to generate the ID."))

        # Safely get the company value, using .get() for robustness.
        company_from_doc = self.get("company")
        logger.debug(f"Autonaming Supplier: '{self.supplier_name}', Company from Doc (if any): '{company_from_doc}'")

        # 1. Get Company Abbreviation
        company_abbr = get_company_abbr(company_from_doc)

        # 2. Get Name Prefix
        name_prefix = get_name_prefix(self.supplier_name)

        # 3. Construct the unique series key for the atomic counter
        # Example: 'SUPP' + 'SPA' + 'ABC' -> "SUPPSPAABC"
        series_key = f"SUPP{name_prefix}{company_abbr}"

        # 4. Get the next sequence number atomically
        try:
            sequence_number = _get_next_series_number_atomic(series_key, padding=DEFAULT_PADDING)
        except Exception as e:
             logger.error(f"Failed to get next series number for key '{series_key}': {str(e)}", exc_info=True)
             frappe.throw(
                 frappe._("Failed to generate the next ID number. Please check the logs or try again. Error: {0}").format(str(e)),
                 title="ID Generation Failed"
             )
             return # Exit autoname

        # 5. Combine parts to form the final document name (ID)
        self.name = f"{name_prefix}{company_abbr}{sequence_number}"
        logger.info(f"Generated Supplier ID: {self.name} for Supplier Name: '{self.supplier_name}', using Company Abbr: '{company_abbr}'")

    def validate(self):
        """
        Validates the Supplier document before saving.

        Ensures Supplier Name is provided.
        Prevents saving if another Supplier exists with the same Supplier Name
        (case-insensitive comparison, ignoring leading/trailing whitespace).
        """
        if not self.supplier_name:
            raise ValidationError(frappe._("Supplier Name cannot be empty."))

        # Normalize the name for comparison
        normalized_supplier_name = cstr(self.supplier_name).strip().lower()
        # Use placeholder for name if document is new
        current_name = self.name if not self.is_new() else "@@@NEW_DOC_PLACEHOLDER@@@"

        # Query for existing suppliers with the same normalized name, excluding self.
        existing = frappe.db.sql("""
            SELECT name, supplier_name
            FROM `tabSupplier`
            WHERE LOWER(TRIM(supplier_name)) = %(normalized_name)s
            AND name != %(current_name)s
            LIMIT 1
        """, {
            "normalized_name": normalized_supplier_name,
            "current_name": current_name
        }, as_dict=True)

        # Handle duplicate finding
        if existing:
            existing_doc = existing[0]
            logger.warning(f"Validation failed: Duplicate supplier name '{self.supplier_name}' found. Existing record: {existing_doc.name}")
            frappe.throw(
                frappe._("A Supplier with the name '{0}' already exists: {1}").format(
                    existing_doc.supplier_name, frappe.bold(existing_doc.name)
                ),
                exc=DuplicateEntryError, # Specify exception type
                title="Duplicate Name"
            )
        logger.debug(f"Supplier validation passed for: {self.name or '(New Document)'}")
