'use client';

import { useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/context/AuthContext';
import { ApiResponseError } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import styles from './LoginForm.module.css';

export function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await login(email.trim(), password);
      router.replace('/dashboard');
    } catch (err) {
      if (err instanceof ApiResponseError) {
        const detail = err.detail;
        setError(typeof detail === 'string' ? detail : detail.join(' '));
      } else {
        setError('Unable to connect. Is the backend running?');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <form
      id="login-form"
      className={styles.form}
      onSubmit={handleSubmit}
      aria-label="Sign in form"
    >
      <div className={styles.field}>
        <label htmlFor="login-email" className={styles.label}>
          Email address
        </label>
        <input
          id="login-email"
          type="email"
          className={styles.input}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="admin@example.com"
          autoComplete="email"
          required
          disabled={loading}
        />
      </div>

      <div className={styles.field}>
        <label htmlFor="login-password" className={styles.label}>
          Password
        </label>
        <input
          id="login-password"
          type="password"
          className={styles.input}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
          autoComplete="current-password"
          required
          disabled={loading}
        />
      </div>

      {error && (
        <p id="login-error" className={styles.error} role="alert">
          {error}
        </p>
      )}

      <Button
        type="submit"
        variant="primary"
        size="lg"
        fullWidth
        loading={loading}
        id="login-submit-btn"
      >
        Sign in
      </Button>
    </form>
  );
}
