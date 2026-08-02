import type { ButtonHTMLAttributes } from 'react'

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
