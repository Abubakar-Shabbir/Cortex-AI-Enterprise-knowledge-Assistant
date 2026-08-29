import {
  AlertTriangle, BadgeCheck, Bell, CheckCircle, FileUp, KeyRound, Megaphone,
  Share2, Shield, ShieldAlert, ShieldOff, Sparkles, UserCheck, UserX, XCircle,
} from 'lucide-react';

// Maps the kebab-case lucide icon names RAG.notification_views._NOTIFICATION_ICONS
// sends (e.g. "share-2") to the matching lucide-react component.
export const NOTIFICATION_ICONS = {
  'share-2': Share2,
  'shield-off': ShieldOff,
  'file-up': FileUp,
  'check-circle': CheckCircle,
  'x-circle': XCircle,
  sparkles: Sparkles,
  'alert-triangle': AlertTriangle,
  'badge-check': BadgeCheck,
  'key-round': KeyRound,
  shield: Shield,
  'shield-alert': ShieldAlert,
  'user-x': UserX,
  'user-check': UserCheck,
  megaphone: Megaphone,
  bell: Bell,
};

export function notificationIcon(name) {
  return NOTIFICATION_ICONS[name] || Bell;
}
