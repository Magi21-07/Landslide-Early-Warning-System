export interface RiskStyle {
  id: string;
  label: string;
  fillColor: string;
  outlineColor: string;
  markerColor: string;
  textColor: string;
  badgeBg: string;
}

export const RISK_LEVELS: Record<string, RiskStyle> = {
  'LOW': {
    id: 'LOW',
    label: 'Low Risk',
    fillColor: '#10b981', // emerald-500
    outlineColor: '#047857', // emerald-700
    markerColor: '#10b981',
    textColor: 'text-emerald-700',
    badgeBg: 'bg-emerald-100',
  },
  'MODERATE': {
    id: 'MODERATE',
    label: 'Moderate Risk',
    fillColor: '#f59e0b', // amber-500
    outlineColor: '#b45309', // amber-700
    markerColor: '#f59e0b',
    textColor: 'text-amber-700',
    badgeBg: 'bg-amber-100',
  },
  'HIGH': {
    id: 'HIGH',
    label: 'High Risk',
    fillColor: '#ef4444', // red-500
    outlineColor: '#b91c1c', // red-700
    markerColor: '#ef4444',
    textColor: 'text-red-700',
    badgeBg: 'bg-red-100',
  },
  'CRITICAL': {
    id: 'CRITICAL',
    label: 'Critical Risk',
    fillColor: '#7f1d1d', // red-900
    outlineColor: '#450a0a', // red-950
    markerColor: '#7f1d1d',
    textColor: 'text-red-900',
    badgeBg: 'bg-red-200',
  },
  'UNKNOWN': {
    id: 'UNKNOWN',
    label: 'Unknown',
    fillColor: '#94a3b8', // slate-400
    outlineColor: '#475569', // slate-600
    markerColor: '#94a3b8',
    textColor: 'text-slate-700',
    badgeBg: 'bg-slate-100',
  }
};

export const getRiskStyle = (level?: string | null): RiskStyle => {
  const normalizedLevel = (level || '').toString().trim().toUpperCase();
  return RISK_LEVELS[normalizedLevel] || RISK_LEVELS['UNKNOWN'];
};

export const getMapPaintMatchExpression = (property: string, fallbackColor: string, styleKey: keyof RiskStyle): any => {
  return [
    'match',
    ['get', property],
    'LOW', RISK_LEVELS['LOW'][styleKey],
    'Low', RISK_LEVELS['LOW'][styleKey],
    'low', RISK_LEVELS['LOW'][styleKey],
    'MODERATE', RISK_LEVELS['MODERATE'][styleKey],
    'Moderate', RISK_LEVELS['MODERATE'][styleKey],
    'moderate', RISK_LEVELS['MODERATE'][styleKey],
    'HIGH', RISK_LEVELS['HIGH'][styleKey],
    'High', RISK_LEVELS['HIGH'][styleKey],
    'high', RISK_LEVELS['HIGH'][styleKey],
    'CRITICAL', RISK_LEVELS['CRITICAL'][styleKey],
    'Critical', RISK_LEVELS['CRITICAL'][styleKey],
    'critical', RISK_LEVELS['CRITICAL'][styleKey],
    fallbackColor
  ];
};
