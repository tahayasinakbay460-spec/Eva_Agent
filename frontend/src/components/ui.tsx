"use client";

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

export function TextField({
  label,
  hint,
  ...input
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  return (
    <label className="block text-sm">
      <span className="text-muted">{label}</span>
      <input
        {...input}
        className="mt-1 w-full rounded-xl border border-border bg-bg-0/60 px-4 py-3 text-base outline-none focus:border-accent"
      />
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export function Checkbox({
  checked,
  onChange,
  children,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  children: ReactNode;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3 text-sm leading-snug">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--color-accent)]"
      />
      <span>{children}</span>
    </label>
  );
}

export function PrimaryButton({
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { children: ReactNode }) {
  return (
    <button
      type="button"
      {...props}
      className="w-full rounded-xl bg-gradient-to-r from-accent to-accent-2 py-3 font-semibold text-white disabled:opacity-50"
    >
      {children}
    </button>
  );
}

export function SecondaryButton({
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { children: ReactNode }) {
  return (
    <button
      type="button"
      {...props}
      className="w-full py-1 text-sm text-muted underline-offset-4 hover:underline disabled:opacity-50"
    >
      {children}
    </button>
  );
}

export function ErrorText({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="text-xs text-red-300">
      {children}
    </p>
  );
}

export function Heading({ title, body }: { title: string; body?: string }) {
  return (
    <div>
      <h1 className="text-2xl font-semibold">{title}</h1>
      {body && <p className="mt-1 text-sm text-muted">{body}</p>}
    </div>
  );
}
