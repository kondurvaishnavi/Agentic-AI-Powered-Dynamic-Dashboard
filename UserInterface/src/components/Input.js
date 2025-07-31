import React, { forwardRef } from 'react';
import './Input.css';

const Input = forwardRef(function Input(
  { error, className = '', ...props },
  ref
) {
  return (
    <div className={`input-wrapper ${className}`}>
      <input ref={ref} className="input-field" {...props} />
      {error && <p className="input-error">{error}</p>}
    </div>
  );
});

export default Input;
