/**
 * Image with a built-in fallback, so a missing upload shows a placeholder
 * rather than a broken box. Used by the owner panels and the customer menu.
 */
interface ThumbProps {
  url?: string | null
  alt: string
  /** 'cover' for restaurant imagery, 'item' for a menu row. */
  variant?: 'cover' | 'item'
}

export function Thumb({ url, alt, variant = 'item' }: ThumbProps) {
  const base = variant === 'cover' ? 'image-thumb' : 'item-thumb'

  if (!url) {
    const placeholder = variant === 'cover' ? 'image-placeholder' : 'item-placeholder'
    return (
      <div className={`${base} ${placeholder}`} aria-hidden>
        {variant === 'cover' ? 'No image' : '🍽'}
      </div>
    )
  }

  // Uploads are served by the API, which the dev server proxies under /api.
  return <img className={base} src={`/api${url}`} alt={alt} />
}
