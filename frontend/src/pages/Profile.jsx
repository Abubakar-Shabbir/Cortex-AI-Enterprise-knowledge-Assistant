import { useEffect, useRef, useState } from 'react';
import {
  AlertCircle, Bell, Camera, Globe, Monitor,
  MonitorSmartphone, Moon, Shield, Smartphone, Sun, Tablet, X,
} from 'lucide-react';

// lucide-react 1.x dropped brand/logo icons (Github, Linkedin, ...) -
// minimal inline marks instead of pulling in a separate icon package.
function LinkedinIcon(props) {
  return (
    <svg viewBox="0 0 24 24" width="1em" height="1em" fill="currentColor" {...props}>
      <path d="M20.45 20.45h-3.56v-5.57c0-1.33-.02-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.34V9h3.41v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.45v6.29zM5.34 7.43a2.07 2.07 0 1 1 0-4.13 2.07 2.07 0 0 1 0 4.13zM7.11 20.45H3.56V9h3.56v11.45z" />
    </svg>
  );
}
function GithubIcon(props) {
  return (
    <svg viewBox="0 0 24 24" width="1em" height="1em" fill="currentColor" {...props}>
      <path d="M12 2C6.48 2 2 6.58 2 12.2c0 4.5 2.87 8.32 6.84 9.67.5.1.68-.22.68-.49 0-.24-.01-.87-.01-1.71-2.78.62-3.37-1.36-3.37-1.36-.45-1.18-1.11-1.49-1.11-1.49-.91-.64.07-.63.07-.63 1 .07 1.53 1.05 1.53 1.05.89 1.56 2.34 1.11 2.91.85.09-.66.35-1.11.63-1.37-2.22-.26-4.56-1.14-4.56-5.06 0-1.12.39-2.03 1.03-2.75-.1-.26-.45-1.31.1-2.72 0 0 .84-.28 2.75 1.05a9.29 9.29 0 0 1 5 0c1.91-1.33 2.75-1.05 2.75-1.05.55 1.41.2 2.46.1 2.72.64.72 1.03 1.63 1.03 2.75 0 3.93-2.35 4.79-4.58 5.05.36.32.68.94.68 1.9 0 1.37-.01 2.47-.01 2.81 0 .27.18.6.69.49A10.02 10.02 0 0 0 22 12.2C22 6.58 17.52 2 12 2z" />
    </svg>
  );
}
import PageHeader from '../components/PageHeader';
import AppLoader from '../components/AppLoader';
import Spinner from '../components/Spinner';
import { timeAgo } from '../lib/timeAgo';
import { useTheme } from '../hooks/useTheme';
import { useSession } from '../auth/SessionContext';
import {
  useChangePassword, useProfile, useUpdateExtendedProfile, useUpdateNotificationPreferences,
  useUpdatePersonal, useUploadAvatar,
} from '../api/hooks';

function formatDate(iso, withTime = false) {
  if (!iso) return withTime ? 'Never' : '—';
  const d = new Date(iso);
  const date = d.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' });
  if (!withTime) return date;
  const time = d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
  return `${date} ${time}`;
}

const HEALTH_CLASSES = {
  success: 'bg-success/10 text-success dark:text-success-dark',
  warning: 'bg-warning/10 text-warning dark:text-warning-dark',
  danger: 'bg-danger/10 text-danger dark:text-danger-dark',
  neutral: 'bg-muted/10 text-muted dark:text-muted-dark',
};

const DEVICE_ICONS = { Mobile: Smartphone, Tablet: Tablet };

function TagInput({ items, onChange, placeholder, tone = 'primary' }) {
  const [value, setValue] = useState('');
  const toneClass = tone === 'primary'
    ? 'bg-primary/10 text-primary dark:text-primary-soft'
    : 'bg-accent/10 text-accent';
  const removeToneClass = tone === 'primary'
    ? 'text-primary/70 hover:bg-primary/20 hover:text-primary'
    : 'text-accent/70 hover:bg-accent/20 hover:text-accent';

  const add = () => {
    const v = value.trim();
    if (v && !items.includes(v)) onChange([...items, v]);
    setValue('');
  };

  return (
    <div>
      <div className="mb-1.5 flex flex-wrap gap-1.5">
        {items.map((item, idx) => (
          <span key={item} className={`inline-flex items-center gap-1 rounded-full py-1 pl-2.5 pr-1.5 text-xs font-medium ${toneClass}`}>
            {item}
            <button type="button" onClick={() => onChange(items.filter((_, i) => i !== idx))} className={`flex h-3.5 w-3.5 items-center justify-center rounded-full ${removeToneClass}`}>
              <X className="h-2.5 w-2.5" />
            </button>
          </span>
        ))}
        {items.length === 0 && <span className="text-xs text-muted dark:text-muted-dark">None added.</span>}
      </div>
      <div className="flex gap-2">
        <input
          type="text" value={value} onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
          placeholder={placeholder}
          className="w-full rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark"
        />
        <button type="button" onClick={add} className="shrink-0 rounded-lg border border-line px-3 text-sm font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Add</button>
      </div>
    </div>
  );
}

// Port of templates/profile.html — one card, several independent
// forms (personal / extended / avatar / notifications / password),
// each saved through its own /api/profile/* endpoint.
export default function Profile() {
  const { data, isLoading } = useProfile();
  const { refresh } = useSession();
  const { isDark, toggle } = useTheme();

  const updatePersonal = useUpdatePersonal();
  const updateExtended = useUpdateExtendedProfile();
  const uploadAvatar = useUploadAvatar();
  const updateNotifications = useUpdateNotificationPreferences();
  const changePassword = useChangePassword();

  const fileInputRef = useRef(null);

  const [personal, setPersonal] = useState(null);
  const [extended, setExtended] = useState(null);
  const [skills, setSkills] = useState([]);
  const [certifications, setCertifications] = useState([]);
  const [disabledCategories, setDisabledCategories] = useState([]);
  const [passwordFields, setPasswordFields] = useState({ old_password: '', new_password1: '', new_password2: '' });
  const [passwordErrors, setPasswordErrors] = useState({});
  const [savedBanner, setSavedBanner] = useState('');

  useEffect(() => {
    if (!data) return;
    setPersonal({ first_name: data.user.first_name, last_name: data.user.last_name, email: data.user.email });
    setExtended({
      headline: data.profile.headline, job_title: data.profile.job_title, department: data.profile.department,
      team: data.profile.team, manager_id: data.profile.manager_id || '', phone: data.profile.phone,
      employee_id: data.profile.employee_id, location: data.profile.location, timezone: data.profile.timezone,
      language: data.profile.language, profile_visibility: data.profile.profile_visibility,
      linkedin_url: data.profile.linkedin_url, github_url: data.profile.github_url, portfolio_url: data.profile.portfolio_url,
    });
    setSkills(data.profile.skills || []);
    setCertifications(data.profile.certifications || []);
    setDisabledCategories(data.notification_preferences.disabled_email_categories || []);
  }, [data]);

  if (isLoading || !data || !personal) return <AppLoader variant="page" />;

  const flashSaved = (msg) => {
    setSavedBanner(msg);
    setTimeout(() => setSavedBanner(''), 2500);
  };

  const onAvatarChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await uploadAvatar.mutateAsync(file);
  };

  const onSavePersonal = async (e) => {
    e.preventDefault();
    await updatePersonal.mutateAsync(personal);
    flashSaved('Profile updated.');
  };

  const onSaveExtended = async (e) => {
    e.preventDefault();
    await updateExtended.mutateAsync({ ...extended, skills, certifications });
    flashSaved('Profile details updated.');
  };

  const onSaveNotifications = async (e) => {
    e.preventDefault();
    const toggleable = data.toggleable_email_categories.map((c) => c.key);
    const enabled = toggleable.filter((k) => !disabledCategories.includes(k));
    await updateNotifications.mutateAsync(enabled);
    flashSaved('Notification preferences updated.');
  };

  const onChangePassword = async (e) => {
    e.preventDefault();
    setPasswordErrors({});
    try {
      await changePassword.mutateAsync(passwordFields);
      setPasswordFields({ old_password: '', new_password1: '', new_password2: '' });
      flashSaved('Password updated.');
      refresh();
    } catch (err) {
      setPasswordErrors(err.data?.errors || {});
    }
  };

  const { user, profile, completion, activity_summary: activitySummary, is_online: isOnline, account_health: accountHealth, last_active: lastActive, manager_options: managerOptions, timezone_choices: timezoneChoices, language_choices: languageChoices, visibility_choices: visibilityChoices, current_device: currentDevice, login_history: loginHistory, active_sessions: activeSessions } = data;

  const DeviceIcon = DEVICE_ICONS[currentDevice.device_type] || Monitor;
  const initials = `${(user.first_name || user.username || '?')[0] || ''}${(user.last_name || '')[0] || ''}`.toUpperCase();

  return (
    <>
      <PageHeader title="Profile" subtitle="Your identity, work details, and account security." />

      {savedBanner && (
        <div className="fade-in-up mb-4 rounded-lg border border-success/20 bg-success/10 px-3.5 py-2.5 text-sm text-success dark:text-success-dark">
          {savedBanner}
        </div>
      )}

      {/* Compact header */}
      <div className="mb-4 overflow-hidden rounded-2xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
        <div className="h-14 bg-gradient-to-r from-primary-light to-primary-dark"></div>
        <div className="px-5 pb-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="group relative -mt-9 shrink-0">
              <label className="relative block cursor-pointer" title="Change profile photo">
                {profile.avatar_url ? (
                  <img src={profile.avatar_url} alt="" className="h-[72px] w-[72px] rounded-full object-cover ring-4 ring-card dark:ring-card-dark" />
                ) : (
                  <div className="flex h-[72px] w-[72px] items-center justify-center rounded-full bg-gradient-to-br from-primary-light to-primary-dark text-xl font-semibold text-white ring-4 ring-card dark:ring-card-dark">
                    {initials}
                  </div>
                )}
                <span className="absolute inset-0 flex items-center justify-center rounded-full bg-black/45 opacity-0 transition-opacity group-hover:opacity-100">
                  {uploadAvatar.isPending ? <Spinner size={16} className="text-white" /> : <Camera className="h-4 w-4 text-white" />}
                </span>
                <input ref={fileInputRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={onAvatarChange} />
              </label>
              <span className={`absolute bottom-0.5 right-0.5 h-3 w-3 rounded-full ring-2 ring-card dark:ring-card-dark ${isOnline ? 'bg-success' : 'bg-muted'}`} title={isOnline ? 'Online' : 'Offline'}></span>
            </div>

            <div className="min-w-0 flex-1 pb-0.5">
              <div className="flex flex-wrap items-center gap-1.5">
                <h2 className="truncate text-base font-bold text-ink dark:text-ink-dark">{`${user.first_name} ${user.last_name}`.trim() || user.username}</h2>
                <span className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${HEALTH_CLASSES[accountHealth.category] || HEALTH_CLASSES.neutral}`}>
                  {accountHealth.label}
                </span>
                <span className="inline-flex items-center gap-1 rounded-full bg-accent/10 px-1.5 py-0.5 text-[10px] font-medium text-accent">
                  <Shield className="h-2.5 w-2.5" /> {user.role_name || 'Unassigned'}
                </span>
              </div>
              <p className={`mt-0.5 text-xs ${profile.headline ? 'font-medium text-primary dark:text-primary-soft' : 'italic text-muted dark:text-muted-dark'}`}>
                {profile.headline || 'No professional headline set yet'}
              </p>
              <p className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-[11px] text-muted dark:text-muted-dark">
                <span className="flex items-center gap-1">
                  <span className={`h-1.5 w-1.5 rounded-full ${isOnline ? 'bg-success' : 'bg-muted'}`}></span>
                  {isOnline ? 'Online now' : `Last active ${timeAgo(lastActive)} ago`}
                </span>
                {profile.job_title && <span>{profile.job_title}</span>}
                {profile.department && <span>· {profile.department}</span>}
              </p>
            </div>

            <div className="shrink-0">
              <span className="text-lg font-bold tracking-tight text-ink dark:text-ink-dark">{completion.percent}%</span>
              <span className="text-[11px] text-muted dark:text-muted-dark"> complete</span>
              <div className="mt-1 h-1.5 w-28 overflow-hidden rounded-full bg-line/60 dark:bg-white/10">
                <div
                  className={`h-full rounded-full ${completion.percent >= 80 ? 'bg-success' : completion.percent >= 50 ? 'bg-primary' : 'bg-warning'}`}
                  style={{ width: `${completion.percent}%` }}
                ></div>
              </div>
            </div>
          </div>

          {completion.missing?.length > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-line pt-3 dark:border-line-dark">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Missing:</span>
              {completion.missing_with_tips.map(([label, tip]) => (
                <span key={label} className="cursor-help rounded-full bg-warning/10 px-2 py-0.5 text-[11px] font-medium text-warning dark:text-warning-dark" title={tip}>{label}</span>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">

          {/* Profile Details */}
          <div className="rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
            <div className="border-b border-line px-5 py-3 dark:border-line-dark">
              <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Profile Details</h2>
            </div>

            <form onSubmit={onSavePersonal} className="space-y-3 px-5 py-4">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Personal</p>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">First Name</label>
                  <input type="text" value={personal.first_name} onChange={(e) => setPersonal({ ...personal, first_name: e.target.value })}
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Last Name</label>
                  <input type="text" value={personal.last_name} onChange={(e) => setPersonal({ ...personal, last_name: e.target.value })}
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Email</label>
                  <input type="email" value={personal.email} onChange={(e) => setPersonal({ ...personal, email: e.target.value })}
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
                </div>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Username</label>
                  <input type="text" value={user.username} disabled
                    className="w-full cursor-not-allowed rounded-lg border border-line bg-line/40 px-3 py-2 text-sm text-muted dark:border-line-dark dark:bg-white/5 dark:text-muted-dark" />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Join Date</label>
                  <input type="text" value={formatDate(user.date_joined)} disabled
                    className="w-full cursor-not-allowed rounded-lg border border-line bg-line/40 px-3 py-2 text-sm text-muted dark:border-line-dark dark:bg-white/5 dark:text-muted-dark" />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Last Login</label>
                  <input type="text" value={formatDate(user.last_login, true)} disabled
                    className="w-full cursor-not-allowed rounded-lg border border-line bg-line/40 px-3 py-2 text-sm text-muted dark:border-line-dark dark:bg-white/5 dark:text-muted-dark" />
                </div>
              </div>

              <div className="flex justify-end pt-1">
                <button type="submit" disabled={updatePersonal.isPending} className="flex items-center gap-1.5 rounded-lg bg-primary px-3.5 py-2 text-xs font-semibold text-white transition-colors hover:bg-primary-dark disabled:opacity-70">
                  {updatePersonal.isPending && <Spinner size={12} />} Save
                </button>
              </div>
            </form>

            <form onSubmit={onSaveExtended} className="space-y-3 border-t border-line px-5 py-4 dark:border-line-dark">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Work</p>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Professional Headline</label>
                <input type="text" maxLength={150} value={extended.headline} onChange={(e) => setExtended({ ...extended, headline: e.target.value })}
                  placeholder="AI Engineer | RAG Systems | Knowledge Intelligence"
                  className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Job Title</label>
                  <input type="text" value={extended.job_title} onChange={(e) => setExtended({ ...extended, job_title: e.target.value })}
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Department</label>
                  <input type="text" value={extended.department} onChange={(e) => setExtended({ ...extended, department: e.target.value })}
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Team</label>
                  <input type="text" value={extended.team} onChange={(e) => setExtended({ ...extended, team: e.target.value })}
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
                </div>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Manager</label>
                  <select value={extended.manager_id} onChange={(e) => setExtended({ ...extended, manager_id: e.target.value })}
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark">
                    <option value="">— None —</option>
                    {managerOptions.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Phone</label>
                  <input type="text" value={extended.phone} onChange={(e) => setExtended({ ...extended, phone: e.target.value })}
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Employee ID</label>
                  <input type="text" value={extended.employee_id} onChange={(e) => setExtended({ ...extended, employee_id: e.target.value })}
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
                </div>
              </div>

              <div>
                <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Location</label>
                <input type="text" value={extended.location} onChange={(e) => setExtended({ ...extended, location: e.target.value })} placeholder="City, Country"
                  className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
              </div>

              <p className="border-t border-line pt-3 text-[11px] font-semibold uppercase tracking-wide text-muted dark:border-line-dark dark:text-muted-dark">Skills & Certifications</p>
              <TagInput items={skills} onChange={setSkills} placeholder="Add a skill and press Enter" tone="primary" />
              <TagInput items={certifications} onChange={setCertifications} placeholder="Add a certification and press Enter" tone="accent" />

              <p className="border-t border-line pt-3 text-[11px] font-semibold uppercase tracking-wide text-muted dark:border-line-dark dark:text-muted-dark">Social Links</p>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div>
                  <label className="mb-1 flex items-center gap-1 text-xs font-medium text-muted dark:text-muted-dark"><LinkedinIcon className="h-3 w-3" /> LinkedIn</label>
                  <input type="url" value={extended.linkedin_url} onChange={(e) => setExtended({ ...extended, linkedin_url: e.target.value })} placeholder="linkedin.com/in/..."
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
                </div>
                <div>
                  <label className="mb-1 flex items-center gap-1 text-xs font-medium text-muted dark:text-muted-dark"><GithubIcon className="h-3 w-3" /> GitHub</label>
                  <input type="url" value={extended.github_url} onChange={(e) => setExtended({ ...extended, github_url: e.target.value })} placeholder="github.com/..."
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
                </div>
                <div>
                  <label className="mb-1 flex items-center gap-1 text-xs font-medium text-muted dark:text-muted-dark"><Globe className="h-3 w-3" /> Portfolio</label>
                  <input type="url" value={extended.portfolio_url} onChange={(e) => setExtended({ ...extended, portfolio_url: e.target.value })} placeholder="yourdomain.com"
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
                </div>
              </div>

              <p className="border-t border-line pt-3 text-[11px] font-semibold uppercase tracking-wide text-muted dark:border-line-dark dark:text-muted-dark">Preferences</p>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Time Zone</label>
                  <select value={extended.timezone} onChange={(e) => setExtended({ ...extended, timezone: e.target.value })}
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark">
                    <option value="">— Not set —</option>
                    {timezoneChoices.map((tz) => <option key={tz} value={tz}>{tz}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Language</label>
                  <select value={extended.language} onChange={(e) => setExtended({ ...extended, language: e.target.value })}
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark">
                    {languageChoices.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Profile Visibility</label>
                  <select value={extended.profile_visibility} onChange={(e) => setExtended({ ...extended, profile_visibility: e.target.value })}
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark">
                    {visibilityChoices.map((v) => <option key={v.value} value={v.value}>{v.label}</option>)}
                  </select>
                </div>
              </div>

              <div className="flex items-center justify-between pt-1">
                <button type="button" onClick={toggle} className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">
                  {isDark ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
                  <span>{isDark ? 'Dark' : 'Light'}</span>
                </button>
                <button type="submit" disabled={updateExtended.isPending} className="flex items-center gap-1.5 rounded-lg bg-primary px-3.5 py-2 text-xs font-semibold text-white transition-colors hover:bg-primary-dark disabled:opacity-70">
                  {updateExtended.isPending && <Spinner size={12} />} Save
                </button>
              </div>
            </form>
          </div>

          {/* Security */}
          <div className="rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
            <div className="border-b border-line px-5 py-3 dark:border-line-dark">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-ink dark:text-ink-dark">
                <Shield className="h-4 w-4 text-primary dark:text-primary-soft" /> Security
              </h2>
            </div>
            <form onSubmit={onChangePassword} className="space-y-3 px-5 py-4">
              {passwordErrors.__all__ && (
                <div className="flex items-start gap-2 rounded-lg border border-danger/20 bg-danger/10 px-3 py-2 text-sm text-danger dark:text-danger-dark">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /> {passwordErrors.__all__[0]}
                </div>
              )}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Current Password</label>
                  <input type="password" value={passwordFields.old_password} onChange={(e) => setPasswordFields({ ...passwordFields, old_password: e.target.value })}
                    className={`w-full rounded-lg border ${passwordErrors.old_password ? 'border-danger' : 'border-line dark:border-line-dark'} bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:bg-white/5 dark:text-ink-dark`} />
                  {passwordErrors.old_password && <p className="mt-1 text-xs text-danger dark:text-danger-dark">{passwordErrors.old_password[0]}</p>}
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">New Password</label>
                  <input type="password" value={passwordFields.new_password1} onChange={(e) => setPasswordFields({ ...passwordFields, new_password1: e.target.value })}
                    className={`w-full rounded-lg border ${passwordErrors.new_password1 ? 'border-danger' : 'border-line dark:border-line-dark'} bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:bg-white/5 dark:text-ink-dark`} />
                  {passwordErrors.new_password1 && <p className="mt-1 text-xs text-danger dark:text-danger-dark">{passwordErrors.new_password1[0]}</p>}
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Confirm New Password</label>
                  <input type="password" value={passwordFields.new_password2} onChange={(e) => setPasswordFields({ ...passwordFields, new_password2: e.target.value })}
                    className={`w-full rounded-lg border ${passwordErrors.new_password2 ? 'border-danger' : 'border-line dark:border-line-dark'} bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:bg-white/5 dark:text-ink-dark`} />
                  {passwordErrors.new_password2 && <p className="mt-1 text-xs text-danger dark:text-danger-dark">{passwordErrors.new_password2[0]}</p>}
                </div>
              </div>
              <div className="flex justify-end">
                <button type="submit" disabled={changePassword.isPending} className="flex items-center gap-1.5 rounded-lg border border-line px-3.5 py-2 text-xs font-semibold text-ink transition-colors hover:bg-surface disabled:opacity-70 dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">
                  {changePassword.isPending && <Spinner size={12} />} Update Password
                </button>
              </div>
            </form>
          </div>

          {/* Notification Preferences */}
          <div className="rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
            <div className="border-b border-line px-5 py-3 dark:border-line-dark">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-ink dark:text-ink-dark">
                <Bell className="h-4 w-4 text-primary dark:text-primary-soft" /> Notification Preferences
              </h2>
            </div>
            <form onSubmit={onSaveNotifications} className="space-y-3 px-5 py-4">
              <p className="text-xs text-muted dark:text-muted-dark">Choose which notifications also send you an email. In-app notifications always appear in your Notification Center regardless of these settings.</p>
              <div className="space-y-2">
                {data.toggleable_email_categories.map(({ key, label, description }) => (
                  <label key={key} className="flex items-start gap-2.5 rounded-lg border border-line px-3 py-2.5 dark:border-line-dark">
                    <input
                      type="checkbox"
                      checked={!disabledCategories.includes(key)}
                      onChange={(e) => setDisabledCategories((prev) => (e.target.checked ? prev.filter((k) => k !== key) : [...prev, key]))}
                      className="mt-0.5 rounded border-line text-primary focus:ring-primary/30 dark:border-line-dark"
                    />
                    <span>
                      <span className="block text-sm font-medium text-ink dark:text-ink-dark">{label}</span>
                      <span className="block text-xs text-muted dark:text-muted-dark">{description}</span>
                    </span>
                  </label>
                ))}
              </div>
              <p className="text-xs text-muted dark:text-muted-dark">Account and security emails (password changes, sign-in verification) always send and can't be turned off.</p>
              <div className="flex justify-end">
                <button type="submit" disabled={updateNotifications.isPending} className="flex items-center gap-1.5 rounded-lg bg-primary px-3.5 py-2 text-xs font-semibold text-white transition-colors hover:bg-primary-dark disabled:opacity-70">
                  {updateNotifications.isPending && <Spinner size={12} />} Save Preferences
                </button>
              </div>
            </form>
          </div>
        </div>

        <div className="space-y-4">
          {/* Activity Summary */}
          <div className="rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
            <div className="border-b border-line px-5 py-3 dark:border-line-dark">
              <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Activity Summary</h2>
            </div>
            <div className="space-y-2 px-5 py-4 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-muted dark:text-muted-dark">Documents Owned</span>
                <span className="font-medium text-ink dark:text-ink-dark">{activitySummary.documents_owned}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted dark:text-muted-dark">Questions Asked</span>
                <span className="font-medium text-ink dark:text-ink-dark">{activitySummary.queries_asked}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted dark:text-muted-dark">AI Task Runs</span>
                <span className="font-medium text-ink dark:text-ink-dark">{activitySummary.ai_task_runs}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted dark:text-muted-dark">Activity Events</span>
                <span className="font-medium text-ink dark:text-ink-dark">{activitySummary.activity_events}</span>
              </div>
              <div className="flex items-center justify-between border-t border-line pt-2 dark:border-line-dark">
                <span className="text-muted dark:text-muted-dark">Member For</span>
                <span className="font-medium text-ink dark:text-ink-dark">{activitySummary.account_age_days} days</span>
              </div>
            </div>
          </div>

          {/* Device & Sessions */}
          <div className="rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
            <div className="border-b border-line px-5 py-3 dark:border-line-dark">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-ink dark:text-ink-dark">
                <MonitorSmartphone className="h-4 w-4 text-primary dark:text-primary-soft" /> Device & Sessions
              </h2>
            </div>
            <div className="space-y-3 px-5 py-4 text-xs">
              <div className="flex items-center gap-2 text-ink dark:text-ink-dark">
                <DeviceIcon className="h-3.5 w-3.5 text-muted dark:text-muted-dark" />
                {currentDevice.device_type} · {currentDevice.browser} · {currentDevice.os}
              </div>

              <div className="border-t border-line pt-2 dark:border-line-dark">
                <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Active Sessions ({activeSessions.length})</p>
                <div className="space-y-1.5">
                  {activeSessions.length === 0 && <p className="text-muted dark:text-muted-dark">No active sessions.</p>}
                  {activeSessions.map((session) => (
                    <div key={session.session_key} className="flex items-center gap-2">
                      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${session.is_current ? 'bg-success' : 'bg-muted'}`}></span>
                      <span className="text-ink dark:text-ink-dark">{session.is_current ? 'This device' : 'Other device'}</span>
                      <span className="text-muted dark:text-muted-dark">· expires {timeAgo(session.expire_date)}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="border-t border-line pt-2 dark:border-line-dark">
                <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Login History</p>
                <div className="space-y-2">
                  {loginHistory.length === 0 && <p className="text-muted dark:text-muted-dark">No login history recorded yet.</p>}
                  {loginHistory.slice(0, 5).map((entry, idx) => (
                    <div key={idx}>
                      <p className="font-medium text-ink dark:text-ink-dark">
                        {formatDate(entry.at, true)} <span className="font-normal text-muted dark:text-muted-dark">({timeAgo(entry.at)} ago)</span>
                      </p>
                      <p className="text-muted dark:text-muted-dark">
                        {entry.device_type} · {entry.browser} · {entry.os}{entry.ip_address ? ` · ${entry.ip_address}` : ''}{entry.location ? ` · ${entry.location}` : ''}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
