import "../polish.css";

const COLORS = ["#9c2a3b", "#d6b98c", "#f5e8d0", "#4ade80", "#e8a87c", "#7b1e2b"];
const PIECES = 36;

// Plays once each time `burst` changes to a new non-zero number.
export default function Confetti({ burst }) {
  if (!burst) return null;

  return (
    <div key={burst} className="dx-confetti" aria-hidden="true">
      {Array.from({ length: PIECES }, (_, i) => (
        <i
          key={i}
          style={{
            "--x": `${(i * 29 + 7) % 100}%`,
            "--d": `${((i * 53) % 40) / 100}s`,
            "--r": `${(i * 47) % 360}deg`,
            "--dx": `${((i * 37) % 160) - 80}px`,
            "--c": COLORS[i % COLORS.length],
          }}
        />
      ))}
    </div>
  );
}
