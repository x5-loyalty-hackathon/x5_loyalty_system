/** Токены взяты из макета «Домовой App.dc.html». Значения менять только вместе с дизайном. */
export const color = {
  bg: '#F2F2F5',
  white: '#FFFFFF',
  ink: '#1A1A1E',
  muted: '#8A8A90',
  body: '#5A5A62',
  line: '#EAEAEE',
  red: '#E4002B',
  redDark: '#C10024',
  redSoft: '#FFF0F2',
  green: '#00A046',
  greenSoft: '#E6F6EC',
  orange: '#FF6A13',
  cream: '#F4E7CD',
  brown: '#4A2E1C',
  iconIdle: '#C9C9D0',
  star: '#FFB800',
  ghost: '#EDEDF1',
  ghostAlt: '#F7F7FA',
  ghostText: '#A9A9B2',
} as const;

export const radius = { card: 16, sheet: 18, pill: 18, phone: 40 } as const;

/** Плейсхолдер вместо фотографии: в макете это диагональная штриховка. */
export const photoStub = { backgroundColor: color.ghost } as const;
