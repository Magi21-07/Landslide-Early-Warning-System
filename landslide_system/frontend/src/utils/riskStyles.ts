export interface RiskStyle {
  id: string;
  label: string;
  fillColor: string;
  outlineColor: string;
  markerColor: string;
  textColor: string;
  badgeBg: string;
}

export const getUnifiedRisk = (target: any): 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL' | 'UNKNOWN' => {
  if (!target) return 'UNKNOWN';
  const riskStr = String(
    target.dynamic_risk || 
    target.risk_level || 
    target.risk ||
    target.severity || 
    target.class || 
    target.properties?.dynamic_risk ||
    target.properties?.risk_level ||
    target.properties?.risk ||
    ''
  ).toUpperCase();

  if (!riskStr) return 'UNKNOWN';
  if (riskStr.includes('CRIT')) return 'CRITICAL';
  if (riskStr.includes('HIGH') || riskStr.includes('RED')) return 'HIGH';
  if (riskStr.includes('MOD') || riskStr.includes('AMBER') || riskStr.includes('WATCH')) return 'MODERATE';
  return 'LOW';
};

export const RISK_LEVELS: Record<string, RiskStyle> = {
  'LOW': {
    id: 'LOW',
    label: 'Low Risk',
    fillColor: '#38A169',
    outlineColor: '#3B82A0',
    markerColor: '#38A169',
    textColor: 'text-[#38A169]',
    badgeBg: 'bg-[#38A169]/10',
  },
  'MODERATE': {
    id: 'MODERATE',
    label: 'Moderate Risk',
    fillColor: '#E6A23C',
    outlineColor: '#E6A23C',
    markerColor: '#E6A23C',
    textColor: 'text-[#E6A23C]',
    badgeBg: 'bg-[#E6A23C]/10',
  },
  'HIGH': {
    id: 'HIGH',
    label: 'High Risk',
    fillColor: '#D94B4B',
    outlineColor: '#D94B4B',
    markerColor: '#D94B4B',
    textColor: 'text-[#D94B4B]',
    badgeBg: 'bg-[#D94B4B]/10',
  },
  'CRITICAL': {
    id: 'CRITICAL',
    label: 'Critical Risk',
    fillColor: '#D94B4B',
    outlineColor: '#D94B4B',
    markerColor: '#D94B4B',
    textColor: 'text-[#D94B4B]',
    badgeBg: 'bg-[#D94B4B]/10',
  },
  'UNKNOWN': {
    id: 'UNKNOWN',
    label: 'Unknown',
    fillColor: '#94a3b8',
    outlineColor: '#475569',
    markerColor: '#94a3b8',
    textColor: 'text-slate-400',
    badgeBg: 'bg-slate-800/50',
  }
};

export const getRiskStyle = (targetOrLevel: any): RiskStyle => {
  if (typeof targetOrLevel === 'string') {
     const unified = getUnifiedRisk({ risk_level: targetOrLevel });
     return RISK_LEVELS[unified];
  }
  const unified = getUnifiedRisk(targetOrLevel);
  return RISK_LEVELS[unified];
};

export const getMapPaintMatchExpression = (property: string, fallbackColor: string, styleKey: keyof RiskStyle): any => {
  return [
    'match',
    ['upcase', ['get', property]],
    'LOW', RISK_LEVELS['LOW'][styleKey],
    'MODERATE', RISK_LEVELS['MODERATE'][styleKey],
    'HIGH', RISK_LEVELS['HIGH'][styleKey],
    'CRITICAL', RISK_LEVELS['CRITICAL'][styleKey],
    fallbackColor
  ];
};
