import { motion } from 'framer-motion'

const VALUES = [
  'Browse kitchens across your city',
  'Track every order, start to doorstep',
  'Pay online or cash on delivery',
]

export function BrandMark({ className = '' }: { className?: string }) {
  return (
    <div className={`brand-mark ${className}`}>
      <span className="dot" aria-hidden />
      tiffin
    </div>
  )
}

export function BrandPanel() {
  return (
    <aside className="brand-panel">
      <BrandMark />

      <motion.div
        className="brand-headline"
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
      >
        <h1>
          Warm meals, <span className="serif-em">delivered</span> to your door.
        </h1>
        <p>
          Order from the restaurants you love and follow every step — from the
          kitchen accepting your order to the rider pulling up outside.
        </p>
      </motion.div>

      <motion.ul
        className="brand-values"
        initial="hidden"
        animate="show"
        variants={{ show: { transition: { staggerChildren: 0.1, delayChildren: 0.3 } } }}
      >
        {VALUES.map((value) => (
          <motion.li
            key={value}
            variants={{ hidden: { opacity: 0, x: -12 }, show: { opacity: 1, x: 0 } }}
          >
            <span className="tick" aria-hidden>
              ✦
            </span>
            {value}
          </motion.li>
        ))}
      </motion.ul>
    </aside>
  )
}
