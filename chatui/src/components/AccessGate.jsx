import { useState } from 'react';
import { ChefHat, KeyRound } from 'lucide-react';

export default function AccessGate({ onSubmit, error }) {
  const [value, setValue] = useState('');
  const submit = (event) => {
    event.preventDefault();
    if (value.trim()) onSubmit(value.trim());
  };
  return <div className="access-gate">
    <div className="access-card soft-outset">
      <span className="logo-mark"><ChefHat size={19} /></span>
      <h2>Welcome back.</h2>
      <p className="muted-copy">Enter your KitchenHQ access key to open the kitchen workspace.</p>
      <form onSubmit={submit}>
        <div className="access-input soft-inset"><KeyRound size={16} /><input type="password" value={value} onChange={(event) => setValue(event.target.value)} placeholder="Access key" autoFocus /></div>
        {error && <div className="error-banner">{error}</div>}
        <button type="submit" className="primary-button" disabled={!value.trim()}>Unlock</button>
      </form>
    </div>
  </div>;
}
