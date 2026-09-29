export function PinIcon({ className = "w-6 h-6" }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden="true">
      <path d="M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7Zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5Z" />
    </svg>
  );
}

export function ClockIcon({ className = "w-6 h-6" }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="10" fill="currentColor" />
      <path d="M12 6v6l3 3" stroke="white" strokeWidth="1.5" fill="none" strokeLinecap="round" />
    </svg>
  );
}

export function DollarIcon({ className = "w-7 h-6" }) {
  return (
    <svg viewBox="0 0 28 22" className={className} aria-hidden="true">
      <rect x="0" y="2" width="28" height="18" fill="currentColor" />
      <text x="14" y="17" textAnchor="middle" fontSize="15" fill="white" fontFamily="Inter, sans-serif">
        $
      </text>
    </svg>
  );
}

export function PushpinIcon({ className = "w-6 h-6" }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden="true">
      <path d="M8 2h8l-1.5 2v5l3.5 4H6l3.5-4V4L8 2Zm3 12h2l-1 8-1-8Z" />
    </svg>
  );
}

export function FlagIcon({ className = "w-6 h-6" }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden="true">
      <path d="M4 3h14l-5 5 5 5H6v9H4V3Z" />
    </svg>
  );
}

export function FunnelIcon({ className = "w-6 h-6" }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden="true">
      <path d="M3 3h18l-7 9v9l-4-2v-7L3 3Z" />
    </svg>
  );
}

export function ChevronDownIcon({ className = "w-4 h-4" }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="m4 8 8 8 8-8" />
    </svg>
  );
}
