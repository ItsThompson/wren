import { forwardRef, useId, type InputHTMLAttributes } from 'react'

import { Input } from '@/components/ui/input'

interface FormInputFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  error?: string
}

export const FormInputField = forwardRef<HTMLInputElement, FormInputFieldProps>(
  function FormInputField(
    { id, label, error, className, 'aria-describedby': describedBy, ...inputProps },
    ref,
  ) {
    const generatedId = useId()
    const inputId = id ?? generatedId
    const errorId = `${inputId}-error`
    const ariaDescribedBy = [describedBy, error ? errorId : undefined].filter(Boolean).join(' ') || undefined

    return (
      <div className="flex flex-col gap-1.5 text-sm">
        <label htmlFor={inputId} className="font-medium text-foreground">
          {label}
        </label>
        <Input
          {...inputProps}
          id={inputId}
          ref={ref}
          className={className}
          aria-invalid={error ? true : undefined}
          aria-describedby={ariaDescribedBy}
        />
        {error && (
          <span id={errorId} className="text-sm text-destructive">
            {error}
          </span>
        )}
      </div>
    )
  },
)
