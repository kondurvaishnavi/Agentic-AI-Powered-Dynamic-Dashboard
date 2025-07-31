import { useState, useEffect, useRef } from 'react';

export function useBearAnimation({
  watchBearImages,
  hideBearImages,
  peakBearImages,
  emailLength,
  showPassword,
}) {
  const [currentFocus, setCurrentFocus] = useState('EMAIL');
  const [currentBearImage, setCurrentBearImage] = useState(null);
  const [isAnimating, setIsAnimating] = useState(false);

  const prevFocus = useRef(currentFocus);
  const prevShowPassword = useRef(showPassword);
  const timeouts = useRef([]);

  // Cleanup timeouts on unmount
  useEffect(() => {
    return () => {
      timeouts.current.forEach(clearTimeout);
    };
  }, []);

  useEffect(() => {
    // Clear existing timeouts
    timeouts.current.forEach(clearTimeout);
    timeouts.current = [];

    const animateImages = (images, interval, reverse = false, onComplete = () => { }) => {
      if (images.length === 0) {
        onComplete();
        return;
      }

      setIsAnimating(true);
      const imageSequence = reverse ? [...images].reverse() : images;

      imageSequence.forEach((img, index) => {
        const timeoutId = setTimeout(() => {
          setCurrentBearImage(img);
          if (index === imageSequence.length - 1) {
            setIsAnimating(false);
            onComplete();
          }
        }, index * interval);
        timeouts.current.push(timeoutId);
      });
    };

    const animateWatchingBearImages = () => {
      const progress = Math.min(emailLength / 30, 1);
      const index = Math.floor(progress * (watchBearImages.length - 1));
      setCurrentBearImage(watchBearImages[Math.max(0, index)]);
      setIsAnimating(false);
    };

    // Animation Logic based on Focus and ShowPassword
    if (currentFocus === 'EMAIL') {
      if (prevFocus.current === 'PASSWORD') {
        animateImages(hideBearImages, 60, true, animateWatchingBearImages);
      } else {
        animateWatchingBearImages();
      }
    } else if (currentFocus === 'PASSWORD') {
      if (prevFocus.current !== 'PASSWORD') {
        // First time entering password field
        animateImages(hideBearImages, 40, false, () => {
          if (showPassword) {
            animateImages(peakBearImages, 50);
          }
        });
      } else if (showPassword && !prevShowPassword.current) {
        animateImages(peakBearImages, 50);
      } else if (!showPassword && prevShowPassword.current) {
        animateImages(peakBearImages, 50, true);
      }
    }

    prevFocus.current = currentFocus;
    prevShowPassword.current = showPassword;
  }, [
    currentFocus,
    showPassword,
    emailLength,
    watchBearImages,
    hideBearImages,
    peakBearImages,
  ]);

  return {
    currentFocus,
    setCurrentFocus,
    currentBearImage:
      currentBearImage ?? (watchBearImages.length > 0 ? watchBearImages[0] : null),
    isAnimating,
  };
}
