import { Mascot } from '../src/mascot'

const NAME = new URLSearchParams(location.search).get('c') ?? 'Cola'

const page: React.CSSProperties = {
  minHeight: '100vh',
  margin: 0,
  display: 'grid',
  gridTemplateColumns: 'minmax(0, 1fr)',
  placeItems: 'center',
  gap: 28,
  background: '#f6f4ef',
  fontFamily: 'ui-sans-serif, system-ui, sans-serif',
  color: '#2b2722',
}

export function App() {
  return (
    <div style={page}>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr)',
          placeItems: 'center',
          gap: 14,
          width: 'min(480px, 100%)',
        }}
      >
        <Mascot
          directions={`/mascots/${NAME}-directions.webp`}
          reactions={`/mascots/${NAME}-reactions.webp`}
          blink={`/mascots/${NAME}-blink.webp`}
          size={200}
          label={NAME}
        />
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            justifyContent: 'center',
            gap: 10,
            fontSize: 13,
            width: '100%',
          }}
        >
          {[
            'Cola',
            'jojo',
            'alien',
            'dragon',
            'frog',
            'otter',
            'owl',
            'penguin',
            'raccoon',
            'robot',
            'tiger',
            'tv',
          ].map((n) => (
            <a
              key={n}
              href={`?c=${n}`}
              style={{
                padding: '5px 12px',
                borderRadius: 999,
                textDecoration: 'none',
                color: n === NAME ? '#f6f4ef' : '#2b2722',
                background: n === NAME ? '#2b2722' : 'rgba(43,39,34,0.08)',
              }}
            >
              {n}
            </a>
          ))}
        </div>
        <p style={{ margin: 0, fontSize: 14, opacity: 0.65 }}>
          Move the cursor anywhere. Click to boop, four times fast for dizzy.
        </p>
      </div>

      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          gap: 40,
          alignItems: 'flex-end',
          width: 'min(480px, 100%)',
        }}
      >
        {[72, 110, 160].map((s) => (
          <Mascot
            key={s}
            directions={`/mascots/${NAME}-directions.webp`}
            reactions={`/mascots/${NAME}-reactions.webp`}
            blink={`/mascots/${NAME}-blink.webp`}
            size={s}
            label={NAME}
          />
        ))}
      </div>
    </div>
  )
}
