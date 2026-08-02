import { clampPhoneInput, DEFAULT_COUNTRY_CODE } from '../../lib/phone'
import { Field } from './Field'
import type { FieldProps } from './Field'

interface PhoneFieldProps extends Omit<FieldProps, 'value' | 'onChange' | 'leading' | 'trailing' | 'type'> {
  value: string
  onChange: (value: string) => void
}

export function PhoneField({ label, value, onChange, id, name, ...rest }: PhoneFieldProps) {
  const fieldId = id ?? name
  const prefixId = `${fieldId}-country-code`
  const usesDefaultCode = !value.trim().startsWith('+')

  return (
    <Field
      {...rest}
      label={label}
      id={fieldId}
      name={name}
      type="tel"
      inputMode="tel"
      autoComplete="tel"
      placeholder={rest.placeholder ?? '9876543210'}
      title={`10 digits for India (+${DEFAULT_COUNTRY_CODE} is added automatically), or +<country code> and the number`}
      value={value}
      onChange={(e) => onChange(clampPhoneInput(e.target.value))}
      aria-describedby={usesDefaultCode ? prefixId : undefined}
      leading={
        usesDefaultCode ? (
          <span className="field-prefix" id={prefixId}>
            +{DEFAULT_COUNTRY_CODE}
          </span>
        ) : null
      }
    />
  )
}
