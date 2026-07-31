// Keystroke filters for name and phone inputs.
//
// These mirror _NAME_RE (`[A-Za-z ]+`) and _PHONE_RE (`\+?\d+`) in
// src/modules/users/schemas.py, which the API enforces on both UserRegister
// and UserUpdate. Filtering here means the user never gets a 422 for a
// character the field was never going to accept.

/** Letters and spaces only — drops digits and special characters. */
export function filterNameInput(value: string): string {
  return value.replace(/[^A-Za-z ]/g, '')
}

/** Digits with at most one leading '+'. */
export function filterPhoneInput(value: string): string {
  return value.replace(/[^\d+]/g, '').replace(/(?!^)\+/g, '')
}
