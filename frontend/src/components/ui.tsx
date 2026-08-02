import { useState } from 'react'
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react'

import { clampPhoneInput, DEFAULT_COUNTRY_CODE } from '../lib/phone'
import type { ToastType } from '../lib/useTimedNotice'

const TOAST_LABELS: Record<ToastType, string> = {
  add: 'Added',
  edit: 'Updated',
  delete: 'Deleted',
}

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
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

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'ghost'
  loading?: boolean
  block?: boolean
}

export function Button({
  variant = 'primary',
  loading = false,
  block = false,
  children,
  className,
  disabled,
  ...rest
}: ButtonProps) {
  const classes = ['btn', `btn-${variant}`, block ? 'btn-block' : '', className ?? '']
    .filter(Boolean)
    .join(' ')
  return (
    <button className={classes} disabled={disabled || loading} {...rest}>
      {loading && <span className="spin" aria-hidden />}
      {children}
    </button>
  )
}

export function Alert({ kind = 'error', children }: { kind?: 'error' | 'ok'; children: ReactNode }) {
  return <div className={`alert alert-${kind}`} role={kind === 'error' ? 'alert' : 'status'}>{children}</div>
}

/**
 * The "nothing to show here" slot every list falls back to — a missing record,
 * an empty result, a section the current role can't use.
 */
export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>
}

/**
 * Placeholder while a list or detail view is still fetching. role="status" so
 * screen readers announce the wait instead of hitting silence.
 */
export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="empty" role="status">
      <span className="spin" aria-hidden /> {label}
    </div>
  )
}

export function Toast({ type, message }: { type: ToastType; message: string }) {
  return (
    <div className={`toast toast-${type}`} role="status" aria-live="polite">
      <span className="toast-type">{TOAST_LABELS[type]}</span>
      <span className="toast-message">{message}</span>
    </div>
  )
}

interface ConfirmDialogProps {
  open: boolean
  title: string
  confirmLabel?: string
  loading?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({
  open,
  title,
  confirmLabel = 'Delete',
  loading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null

  return (
    <div className="confirm-backdrop" onClick={onCancel} role="presentation">
      <div
        className="confirm-dialog card"
        role="alertdialog"
        aria-labelledby="confirm-dialog-title"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <p id="confirm-dialog-title" className="confirm-title">{title}</p>
        <div className="confirm-actions">
          <Button variant="ghost" type="button" onClick={onCancel}>Cancel</Button>
          <Button loading={loading} onClick={onConfirm}>{confirmLabel}</Button>
        </div>
      </div>
    </div>
  )
}
