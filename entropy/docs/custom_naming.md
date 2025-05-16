# Custom Naming for Customer and Supplier

## Overview

This documentation describes the `entropy/utils/custom_naming.py` script, which implements a custom naming convention and duplicate prevention logic for the `Customer` and `Supplier` DocTypes in your Frappe/ERPNext instance.

The primary goals are:
1.  **Standardized Naming:** Ensure all Customer and Supplier IDs follow a consistent, predictable format.
2.  **Concurrency Safety:** Generate unique IDs reliably even when multiple users save documents simultaneously.
3.  **Duplicate Prevention:** Prevent the creation of Customers or Suppliers with identical names (case-insensitive).

## Naming Format

The script generates document names (IDs) in the following format:

`[NAME_PREFIX][COMPANY_ABBR][SEQ_NUM]`

Where:
*   **`[NAME_PREFIX]`**: The first 1-3 uppercase alphanumeric characters of the Customer/Supplier Name (e.g., "SPA" from "Spar Inc."). Defaults to "UNK" if the name is empty or contains no alphanumeric characters. Controlled by `MAX_PREFIX_LENGTH` and `DEFAULT_NAME_PREFIX` constants.
*   **`[COMPANY_ABBR]`**: The abbreviation configured for the relevant company. It first checks the document (though often not present directly on Customer/Supplier), then the user's default company, and finally falls back to "CO". Fetched via `get_company_abbr`. Controlled by `DEFAULT_COMPANY_ABBR`.
*   **`[SEQ_NUM]`**: A zero-padded sequential number (e.g., "001", "042"). The sequence is unique *per combination* of `[NAME_PREFIX]` and `[COMPANY_ABBR]`. The padding width is controlled by the `DEFAULT_PADDING` constant. This number is generated atomically to prevent race conditions.

**Example:**
*   A Customer named "Spar Retail" linked to a Company with abbreviation "ABC" might get the ID: `SPAABC001`.
*   The next Customer named "Spar Wholesale" for the *same company* would get: `SPAABC002`.
*   A Supplier named "Global Supplies" for a company with abbreviation "XYZ" might get: `GLOXYZ001`.

## Key Components

### 1. DocType Classes (`CustomCustomer`, `CustomSupplier`)

These classes extend the base Frappe `Document` class and are intended to be hooked into the `Customer` and `Supplier` DocTypes via `hooks.py`.

*   **`autoname(self)` method:**
    *   This method overrides the default Frappe naming behavior.
    *   It's automatically called by Frappe when a new document is being inserted (`Before Insert` event context).
    *   It constructs the `series_key` (e.g., "CUSTSPAABC").
    *   It calls `_get_next_series_number_atomic` to get the next unique sequence number for that key.
    *   It combines the prefix, abbreviation, and sequence number to set `self.name`.
    *   Requires `customer_name` or `supplier_name` to be set.
*   **`validate(self)` method:**
    *   This method is called by Frappe before saving a document (`Before Save` event context).
    *   It performs a case-insensitive check (`LOWER(TRIM(name_field))`) against existing records in the database.
    *   Crucially, it excludes the document *itself* (`AND name != %(current_name)s`) from the check, allowing updates to existing records.
    *   If a duplicate name is found, it throws a `DuplicateEntryError` with a user-friendly message.
    *   Requires `customer_name` or `supplier_name` to be set.

### 2. Atomic Sequence Generation (`_get_next_series_number_atomic`)

This is the core function for ensuring unique sequence numbers, especially under concurrent user activity.

*   **Problem Solved:** Prevents race conditions where two users saving at the same time might otherwise attempt to generate the same ID.
*   **Mechanism:** Uses the `tabSingles` table (a standard Frappe key-value store) and SQL's `SELECT ... FOR UPDATE` row-locking mechanism.
    *   It attempts to select and lock the row in `tabSingles` corresponding to the unique `series_key` (e.g., "CUSTSPAABC", stored in the `doctype` column) and a fixed field identifier (`current_value`, stored in the `field` column).
    *   If the row exists, it increments the `value` column within the locked transaction.
    *   If the row doesn't exist, it inserts the initial value (usually 1).
    *   Includes handling for a very rare insertion race condition using `try...except DuplicateEntryError`.
*   **Result:** Guarantees that each call for a specific `series_key` gets the next available number sequentially and atomically.

### 3. Helper Functions

*   **`get_company_abbr(company)`:** Safely retrieves the company abbreviation, checking the document, user defaults, and providing a fallback. Uses Frappe's caching for efficiency.
*   **`get_name_prefix(name_field)`:** Cleans the input name (alphanumeric only, uppercase) and extracts the prefix of the configured length. Handles empty or non-standard names gracefully.

### 4. Configuration Constants

Several constants at the top of the file allow easy configuration:
*   `DEFAULT_COMPANY_ABBR`: Fallback company abbreviation.
*   `DEFAULT_NAME_PREFIX`: Fallback name prefix.
*   `DEFAULT_PADDING`: Number of digits for the sequence number (e.g., 3 -> `001`).
*   `MAX_PREFIX_LENGTH`: Maximum length of the name prefix.
*   `SERIES_FIELDNAME_KEY`: The fixed key used in the `field` column of `tabSingles` for these counters.

## Integration

To make this script functional, you need to configure hooks in your app's (`entropy`) `hooks.py` file:

```python
# entropy/hooks.py

doc_events = {
    "Customer": {
        "autoname": "entropy.utils.custom_naming.CustomCustomer.autoname",
        "validate": "entropy.utils.custom_naming.CustomCustomer.validate"
    },
    "Supplier": {
        "autoname": "entropy.utils.custom_naming.CustomSupplier.autoname",
        "validate": "entropy.utils.custom_naming.CustomSupplier.validate"
    }
}
```
