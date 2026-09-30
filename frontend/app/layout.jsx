import 'maplibre-gl/dist/maplibre-gl.css';
import './globals.css';
import Providers from './providers';

export const metadata = {
  title: 'WeatherPulse AI · Detect. Track. Alert. Protect.',
  description: 'AI-driven spatio-temporal tracking of extreme weather anomalies in medium-range forecasts (SIH26078).',
};

export const viewport = { width: 'device-width', initialScale: 1, themeColor: '#14202b' };

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&family=Noto+Sans+Kannada:wght@400;600&display=swap" rel="stylesheet" />
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
