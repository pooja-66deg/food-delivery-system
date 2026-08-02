import type { InputHTMLAttributes, ReactNode } from 'react'

export interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  trailing?: ReactNode
  leading?: ReactNode
}

export function Field({ label, id, name, trailing, leading, ...rest }: FieldProps) {
  const fieldId = id ?? name
  const input = <input id={fieldId} name={name} className="input" {...rest} />
  const wrapped = leading !== undefined || trailing !== undefined
  return (
    <div className="field">
      <label htmlFor={fieldId}>{label}</label>
      {wrapped ? (
        <div className="field-control" data-leading={leading ? '' : undefined}>
          {leading}
          {input}
          {trailing}
        </div>
      ) : (
        input
      )}
    </div>
  )
}
