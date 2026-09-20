# Search indexing compatibility

The donor Settings Intelligence policy-resource probe passes the `-1` default
from `TypedArray.getResourceId()` to `Resources.getResourceEntryName()`.
Missing or literal XML attributes therefore trigger a failed lookup before the
existing exception handler returns false.

Skip that lookup only for the exact `-1` sentinel. Returning false preserves
`XmlParserUtils.getData()` and its existing `TypedArray.getString()` fallback,
including literal strings and absent optional values. Valid resource IDs and
the device-policy resource map retain their original handling.

This module is scoped to beyond1lte. It does not remove search rows, replace
resource IDs, alter translations, or suppress resource errors globally.
