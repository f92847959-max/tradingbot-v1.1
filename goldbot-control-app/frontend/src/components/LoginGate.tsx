import { useState } from "react";

type LoginGateProps = {
  onUnlock: (token: string) => void;
  hint?: string;
};

export function LoginGate({ onUnlock, hint }: LoginGateProps) {
  const [token, setToken] = useState("");
  const [localHint, setLocalHint] = useState(
    hint ?? "Zugriffstoken eingeben, um fortzufahren.",
  );

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const value = token.trim();
    if (!value) {
      setLocalHint("Token darf nicht leer sein.");
      return;
    }
    onUnlock(value);
    setLocalHint("Wird geladen...");
  }

  return (
    <div className="login-wrap">
      <section className="login-card">
        <p className="eyebrow">Privater Modus</p>
        <h1>GoldBot 🔒</h1>
        <p className="subline">
          Gib dein Zugriffstoken ein, um das Trading Dashboard zu entsperren.
        </p>
        <form className="login-form" onSubmit={handleSubmit}>
          <label className="field">
            <span>Token</span>
            <input
              type="password"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder="Token eingeben..."
              autoComplete="off"
            />
          </label>
          <button type="submit">Entsperren</button>
          <p className="helper-line">{hint ?? localHint}</p>
        </form>
      </section>
    </div>
  );
}
