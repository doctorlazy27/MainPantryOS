import { Children, isValidElement, useEffect, useId, useRef, useState, type KeyboardEvent, type ReactElement, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Check, ChevronDown } from 'lucide-react'

type OptionProps = { value?: string | number; disabled?: boolean; children?: ReactNode }
type Option = { value: string; label: ReactNode; disabled: boolean }
type Props = {
  value: string | number
  onChange: (event: { target: { value: string } }) => void
  children: ReactNode
  required?: boolean
  disabled?: boolean
  id?: string
  className?: string
  'aria-label'?: string
}

export default function AppSelect({ value, onChange, children, required = false, disabled = false, id, className = '', 'aria-label': ariaLabel }: Props) {
  const listboxId = useId()
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [mobileSheet, setMobileSheet] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const [menuStyle, setMenuStyle] = useState<{ left: number; top?: number; bottom?: number; width: number; maxHeight: number }>({ left: 8, top: 8, width: 240, maxHeight: 320 })
  const selectedValue = String(value ?? '')
  const options: Option[] = Children.toArray(children).filter(isValidElement).map((child) => {
    const props = (child as ReactElement<OptionProps>).props
    const label = props.children ?? ''
    const optionValue = props.value ?? (typeof label === 'string' || typeof label === 'number' ? label : '')
    return { value: String(optionValue), label, disabled: Boolean(props.disabled) }
  })
  const selectedOption = options.find((option) => option.value === selectedValue)
  const optionText = (label: ReactNode) => typeof label === 'string' || typeof label === 'number' ? String(label) : ''

  function updatePosition() {
    const rect = triggerRef.current?.getBoundingClientRect()
    if (!rect) return
    const maxHeight = Math.max(140, Math.min(320, window.innerHeight - 24))
    const above = window.innerHeight - rect.bottom < Math.min(240, maxHeight) && rect.top > Math.min(240, maxHeight)
    setMenuStyle({
      left: Math.max(8, Math.min(rect.left, window.innerWidth - rect.width - 8)),
      top: above ? undefined : rect.bottom + 6,
      bottom: above ? window.innerHeight - rect.top + 6 : undefined,
      width: rect.width,
      maxHeight,
    })
  }

  function openMenu() {
    if (disabled) return
    const selectedIndex = options.findIndex((option) => option.value === selectedValue && !option.disabled)
    setActiveIndex(selectedIndex >= 0 ? selectedIndex : Math.max(0, options.findIndex((option) => !option.disabled)))
    const useMobileSheet = window.matchMedia('(max-width: 700px)').matches
    setMobileSheet(useMobileSheet)
    if (!useMobileSheet) updatePosition()
    setOpen(true)
  }

  function closeMenu() {
    setOpen(false)
    triggerRef.current?.focus()
  }

  function choose(option: Option) {
    if (option.disabled) return
    onChange({ target: { value: option.value } })
    closeMenu()
  }

  function moveActive(start: number, direction: number) {
    if (!options.length) return start
    let index = start
    for (let step = 0; step < options.length; step += 1) {
      index = (index + direction + options.length) % options.length
      if (!options[index].disabled) return index
    }
    return start
  }

  function onTriggerKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (!open) openMenu()
      else setActiveIndex((index) => moveActive(index, event.key === 'ArrowDown' ? 1 : -1))
    } else if (event.key === 'Home' || event.key === 'End') {
      if (!open) return
      event.preventDefault()
      const indices = options.map((option, index) => option.disabled ? -1 : index).filter((index) => index >= 0)
      if (indices.length) setActiveIndex(event.key === 'Home' ? indices[0] : indices[indices.length - 1])
    } else if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      if (!open) openMenu()
      else if (options[activeIndex]) choose(options[activeIndex])
    } else if (event.key === 'Escape' && open) {
      event.preventDefault()
      closeMenu()
    } else if (event.key === 'Tab' && open) {
      setOpen(false)
    }
  }

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node
      if (!rootRef.current?.contains(target) && !menuRef.current?.contains(target)) setOpen(false)
    }
    const onViewportChange = () => {
      if (!window.matchMedia('(max-width: 700px)').matches) updatePosition()
    }
    document.addEventListener('pointerdown', onPointerDown)
    window.addEventListener('resize', onViewportChange)
    window.addEventListener('scroll', onViewportChange, true)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      window.removeEventListener('resize', onViewportChange)
      window.removeEventListener('scroll', onViewportChange, true)
    }
  }, [open])

  return <div className={`app-select ${className}`} ref={rootRef}>
    <button
      ref={triggerRef}
      type="button"
      className="app-select-trigger"
      role="combobox"
      aria-label={ariaLabel}
      aria-haspopup="listbox"
      aria-expanded={open}
      aria-controls={listboxId}
      aria-activedescendant={open ? `${listboxId}-option-${activeIndex}` : undefined}
      aria-required={required || undefined}
      disabled={disabled}
      onClick={() => open ? closeMenu() : openMenu()}
      onKeyDown={onTriggerKeyDown}
    ><span>{optionText(selectedOption?.label ?? options[0]?.label ?? 'Select option')}</span><ChevronDown size={16} aria-hidden="true" /></button>
    <select
      id={id}
      className="app-select-native"
      tabIndex={-1}
      aria-hidden="true"
      required={required}
      disabled={disabled}
      value={selectedValue}
      onChange={(event) => onChange({ target: { value: event.target.value } })}
      onInvalid={(event) => { event.preventDefault(); openMenu(); triggerRef.current?.focus() }}
    >{children}</select>
    {open && createPortal(<>
      {mobileSheet && <div className="app-select-scrim" aria-hidden="true" onClick={closeMenu} />}
      <div
        ref={menuRef}
        id={listboxId}
        role="listbox"
        aria-label={ariaLabel ?? 'Options'}
        className={`app-select-menu${mobileSheet ? ' mobile' : ''}`}
        style={mobileSheet ? undefined : menuStyle}
      >{options.map((option, index) => <div
        key={`${option.value}:${index}`}
        id={`${listboxId}-option-${index}`}
        role="option"
        aria-selected={option.value === selectedValue}
        aria-disabled={option.disabled || undefined}
        className={`app-select-option${option.value === selectedValue ? ' selected' : ''}${index === activeIndex ? ' active' : ''}${option.disabled ? ' disabled' : ''}`}
        onMouseEnter={() => setActiveIndex(index)}
        onClick={() => choose(option)}
      ><span>{option.label}</span>{option.value === selectedValue && <Check size={16} aria-hidden="true" />}</div>)}</div>
    </>, document.body)}
  </div>
}