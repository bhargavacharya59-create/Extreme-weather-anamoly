import GovShell from '@/components/gov/Shell';

export const metadata = { title: 'WeatherPulse AI · Government' };

export default function GovLayout({ children }) {
  return <GovShell>{children}</GovShell>;
}
