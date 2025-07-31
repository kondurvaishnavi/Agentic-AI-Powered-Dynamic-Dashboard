import { useState, useEffect } from 'react';

export function useBearImages() {
  const [watchBearImages, setWatchBearImages] = useState([]);
  const [hideBearImages, setHideBearImages] = useState([]);
  const [peakBearImages, setPeakBearImages] = useState([]);

  useEffect(() => {
    const loadImages = (prefix, count) => {
      const images = [];
      for (let i = 0; i <= count; i++) {
        images.push(`${process.env.PUBLIC_URL}../assets/img/${prefix}${i}.png`);
      }
      return images;
    };

    // Assuming you have 10 images for each type
    setWatchBearImages(loadImages('watch_bear_', 20));
    setHideBearImages(loadImages('hide_bear_', 5));
    setPeakBearImages(loadImages('peak_bear_', 3));
  }, []);

  return {
    watchBearImages,
    hideBearImages,
    peakBearImages,
  };
}
