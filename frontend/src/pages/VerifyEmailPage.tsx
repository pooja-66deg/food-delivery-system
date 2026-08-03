import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'

import { authApi } from '../api/auth'
import { errorMessage } from '../api/client'
import { BrandPanel } from '../components/BrandPanel'
import { Alert, Loading } from '../components/ui'

type Status = 'working' | 'done' | 'failed'

/**
 * Opened from the emailed link, so it must work signed out — the token in the
 * query string is the credential.
 */
export function VerifyEmailPage() {
  const [params] = useSearchParams()
  const token = params.get('token')
  const [status, setStatus] = useState<Status>('working')
  const [error, setError] = useState<string | null>(null)
  // The token is single-use; StrictMode's double effect would spend it twice
  // and report the second attempt as a failure.
  const attempted = useRef(false)

  useEffect(() => {
    if (attempted.current) return
    attempted.current = true

    if (!token) {
      setStatus('failed')
      setError('This link is missing its verification token.')
      return
    }
    void (async () => {
      try {
        await authApi.confirmEmailVerification(token)
        setStatus('done')
      } catch (err) {
        setError(errorMessage(err, 'This verification link is invalid or has expired.'))
        setStatus('failed')
      }
    })()
  }, [token])

  return (
    <div className="auth-split">
      <BrandPanel />
      <main className="auth-form-panel">
        <motion.div
          className="auth-card"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        >
          <h2>Email verification</h2>

          {status === 'working' && <Loading label="Verifying your email…" />}
          {status === 'done' && <Alert kind="ok">Your email address is verified.</Alert>}
          {status === 'failed' && <Alert>{error}</Alert>}

          <p className="sub" style={{ marginTop: '1.5rem' }}>
            <Link to="/account" className="back-link">← Back to your account</Link>
          </p>
        </motion.div>
      </main>
    </div>
  )
}
