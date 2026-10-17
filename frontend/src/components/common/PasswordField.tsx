import { Eye, EyeOff } from 'lucide-react';
import { useState } from 'react';

/** 密码输入框：带掩码与眼睛切换图标（设计文档 §10.3）。 */
export function PasswordField({
  label,
  value,
  onChange,
  placeholder,
  autoComplete,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  autoComplete?: string;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <span className="input-with-action">
        <input
          className="input-field"
          type={visible ? 'text' : 'password'}
          value={value}
          placeholder={placeholder}
          autoComplete={autoComplete}
          onChange={(event) => onChange(event.target.value)}
        />
        <button
          type="button"
          className="input-action-btn"
          onClick={() => setVisible((current) => !current)}
          title={visible ? '隐藏密码' : '显示密码'}
        >
          {visible ? <EyeOff size={16} /> : <Eye size={16} />}
        </button>
      </span>
    </label>
  );
}
