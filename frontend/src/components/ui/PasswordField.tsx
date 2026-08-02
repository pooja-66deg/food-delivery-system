import { useState } from 'react'

import { Field } from './Field'
import type { FieldProps } from './Field'

type PasswordFieldProps = Omit<FieldProps, 'type' | 'trailing'>

export function PasswordField(props: PasswordFieldProps) {
  const [visible, setVisible] = useState(false)
  const action = visible ? 'Hide password' : 'Show password'

  return (
    <Field
      {...props}
      type={visible ? 'text' : 'password'}
      trailing={
        <button
          type="button"
          className="field-affix"
          onClick={() => setVisible((v) => !v)}
          aria-label={action}
          aria-pressed={visible}
          title={action}
        >
          <EyeIcon crossed={visible} />
        </button>
      }
    />
  )
}

function EyeIcon({ crossed }: { crossed: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden>
      <path d="M1.8 12S5.4 5.4 12 5.4 22.2 12 22.2 12 18.6 18.6 12 18.6 1.8 12 1.8 12Z" />
      <circle cx="12" cy="12" r="3.1" />
      {crossed && <path d="M3.5 3.5l17 17" />}
    </svg>
  )
}
