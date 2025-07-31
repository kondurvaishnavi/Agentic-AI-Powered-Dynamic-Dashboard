import React, { useRef, useState } from 'react';
import { useBearImages } from '../hooks/useBearImages';
import { useBearAnimation } from '../hooks/useBearAnimation';
import BearAvatar from './BearAvatar';
import Input from './Input';
import EyeIconSrc from '../assets/icons/eye_on.svg';
import EyeOffIconSrc from '../assets/icons/eye_off.svg';
import './LoginForm.css';

export default function LoginForm({ values, setValues, handleSubmit }) {
  // const emailRef = useRef(null);
  const passwordRef = useRef(null);
  const [showPassword, setShowPassword] = useState(false);
  const { watchBearImages, hideBearImages, peakBearImages } = useBearImages();

  const {
    currentBearImage,
    setCurrentFocus,
    currentFocus,
    isAnimating,
  } = useBearAnimation({
    watchBearImages,
    hideBearImages,
    peakBearImages,
    emailLength: values.email.length,
    showPassword,
  });

  const togglePassword = () => {
    if (!isAnimating) {
      setShowPassword((prev) => !prev);
    }
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setValues((prev) => ({ ...prev, [name]: value }));
  };

  return (
    <form className="login-form" onSubmit={handleSubmit}>
      <div className="bear-avatar-wrapper">
        {currentBearImage && (
          <BearAvatar
            currentImage={currentBearImage}
            key={`${currentFocus}-${values.email.length}`}
          />
        )}
      </div>

      {/* <Input
        placeholder="Email"
        name="email"
        type="email"
        ref={emailRef}
        autoFocus
        onFocus={() => setCurrentFocus('EMAIL')}
        autoComplete="email"
        value={values.email}
        onChange={handleInputChange}
      /> */}

      <div className="password-wrapper">
        <Input
          placeholder="Api-key"
          name="password"
          type={showPassword ? 'text' : 'password'}
          ref={passwordRef}
          onFocus={() => setCurrentFocus('PASSWORD')}
          autoComplete="current-password"
          value={values.password}
          onChange={handleInputChange}
        />
        <button
          type="button"
          onClick={togglePassword}
          className="toggle-password-btn"
        >
          <img
            src={showPassword ? EyeIconSrc : EyeOffIconSrc}
            alt={showPassword ? 'Hide password' : 'Show password'}
            className="eye-icon"
          />
        </button>
      </div>

      <button type="submit" className="login-btn">
        Validate 
      </button>
    </form>
  );
}
