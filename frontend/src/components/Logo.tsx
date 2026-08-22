/**
 * The Kevin marks, inlined from ../../brand so they paint with `currentColor`
 * and need no asset request. Geometry is the brand file's, untouched.
 */

function Mark({ id }: { id: string }) {
  return (
    <>
      <mask id={id} maskUnits="userSpaceOnUse" x="0" y="0" width="200" height="200">
        <rect width="200" height="200" fill="#fff" />
        <circle cx="100" cy="100" r="21" fill="#000" />
      </mask>
      <g
        fill="currentColor"
        stroke="currentColor"
        strokeWidth="8"
        strokeLinejoin="round"
        mask={`url(#${id})`}
      >
        <path d="M64 28 96.9 47 96.9 85 64 104 31.1 85 31.1 47Z" />
        <path d="M64 96 96.9 115 96.9 153 64 172 31.1 153 31.1 115Z" />
        <path d="M133 62 165.9 81 165.9 119 133 138 100.1 119 100.1 81Z" />
      </g>
      <g fill="currentColor">
        <path d="M94.40 91.60 97.34 93.30 97.34 96.70 94.40 98.40 91.46 96.70 91.46 93.30Z" />
        <path d="M105.60 91.60 108.54 93.30 108.54 96.70 105.60 98.40 102.66 96.70 102.66 93.30Z" />
        <path
          d="M94.00 106.20 95.50 108.80 104.50 108.80 106.00 106.20"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </g>
      <path d="M133 60 143.5 45" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="144.5" cy="43.4" r="2.6" fill="currentColor" />
    </>
  );
}

/** Icon only, square. */
export function KevinMark({ size = 24, className }: { size?: number; className?: string }) {
  return (
    <svg
      viewBox="0 0 200 200"
      width={size}
      height={size}
      fill="none"
      role="img"
      aria-label="Kevin"
      className={className}
    >
      <Mark id="kevin-mark-feed" />
    </svg>
  );
}

/** Icon + wordmark, horizontal. */
export function KevinLockup({ height = 22, className }: { height?: number; className?: string }) {
  return (
    <svg
      viewBox="0 0 395 122"
      height={height}
      width={(height * 395) / 122}
      fill="none"
      role="img"
      aria-label="Kevin"
      className={className}
    >
      <g transform="translate(-21.75,-19.26) scale(0.80263)">
        <Mark id="kevin-lockup-feed" />
      </g>
      <g transform="translate(152.35,-26)">
        <g stroke="currentColor" strokeWidth="9.5" strokeLinecap="butt" strokeLinejoin="round">
          <path d="M5 44V130" />
          <path d="M41 80 9 110 41 130" />
          <path d="M56 104H97" />
          <path d="M97 104A21 21 0 1 0 90.5 120.1" />
          <path d="M112 78 133 130 154 78" />
          <path d="M173 78V130" />
          <path d="M196 130V99A21 21 0 0 1 238 99V130" />
        </g>
        <circle cx="173" cy="60" r="4.9" fill="currentColor" />
      </g>
    </svg>
  );
}
