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

/**
 * Stand-in artwork for a restaurant or dish with no upload yet.
 *
 * Drawn rather than shipped as a file: an inline SVG stays crisp at every size
 * the thumb is used at, needs no network round trip, and picks up the current
 * theme's colours instead of baking in a grey that clashes.
 */
function PlaceholderArt({ variant }: { variant: 'cover' | 'item' }) {
  return (
    <svg
      className="thumb-art"
      viewBox="0 0 64 48"
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
      focusable="false"
    >
      {/* A plate seen from above, with cutlery either side on the cover size.
          The item size drops the cutlery — at 46px it would be mush. */}
      <circle cx="32" cy="24" r="13" fill="none" stroke="currentColor" strokeWidth="2" />
      <circle cx="32" cy="24" r="7" fill="none" stroke="currentColor" strokeWidth="1.4" opacity="0.65" />
      {variant === 'cover' && (
        <g stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" opacity="0.75">
          {/* fork */}
          <path d="M12 12v8a3 3 0 0 0 3 3v13" fill="none" />
          <path d="M18 12v8a3 3 0 0 1-3 3" fill="none" />
          {/* knife */}
          <path d="M50 12c2.5 3 2.5 8 0 11v13" fill="none" />
        </g>
      )}
    </svg>
  )
}

export function Thumb({ url, alt, variant = 'item' }: ThumbProps) {
  const base = variant === 'cover' ? 'image-thumb' : 'item-thumb'

  if (!url) {
    const placeholder = variant === 'cover' ? 'image-placeholder' : 'item-placeholder'
    // aria-hidden: the surrounding card already names the restaurant or dish, so
    // announcing "no image" adds nothing for a screen reader.
    return (
      <div className={`${base} ${placeholder}`} aria-hidden>
        <PlaceholderArt variant={variant} />
      </div>
    )
  }

  // Uploads are served by the API, which the dev server proxies under /api.
  return <img className={base} src={`/api${url}`} alt={alt} />
}
