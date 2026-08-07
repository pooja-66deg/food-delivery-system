import React from 'react'

interface AddressAutocompleteProps {
  value?: string
  onChange?: (value: string) => void
  disabled?: boolean
  placeholder?: string
}

export const AddressAutocomplete: React.FC<AddressAutocompleteProps> = ({
  value = '',
  onChange,
  disabled = false,
  placeholder = 'Street address',
}) => {
  return (
    <div className="field">
      <label>Street Address</label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className="input"
      />
    </div>
  )
}
