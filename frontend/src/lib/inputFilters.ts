// Keystroke filters for name and phone inputs.
//
// filterNameInput mirrors _NAME_RE (`[A-Za-z ]+`) in
// src/modules/users/schemas.py, which the API enforces on both UserRegister
// and UserUpdate. Filtering here means the user never gets a 422 for a
// character the field was never going to accept.
//
// Phone *shape* is a separate concern — see lib/phone.ts, which turns whatever
// survives this filter into E.164 on submit.

/** Letters and spaces only — drops digits and special characters. */
export function filterNameInput(value: string): string {
  return value.replace(/[^A-Za-z ]/g, '')
}

/** Digits with at most one leading '+'. */
export function filterPhoneInput(value: string): string {
  return value.replace(/[^\d+]/g, '').replace(/(?!^)\+/g, '')
}
