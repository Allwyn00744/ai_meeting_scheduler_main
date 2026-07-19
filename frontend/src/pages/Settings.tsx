import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Bell, Calendar, CheckCircle2, Hash, MailWarning, MessageCircle, Users, Video } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { usePushNotifications } from "@/hooks/usePushNotifications";
import { usersApi } from "@/api/users";
import { googleApi } from "@/api/google";
import { outlookApi } from "@/api/outlook";
import { zoomApi } from "@/api/zoom";
import { teamsApi } from "@/api/teams";
import { slackApi } from "@/api/slack";
import { whatsappApi } from "@/api/whatsapp";
import { pushApi } from "@/api/push";
import { getApiErrorMessage } from "@/api/client";

const TABS = [
  "Profile",
  "Google Calendar",
  "Outlook Calendar",
  "Zoom Meetings",
  "Microsoft Teams",
  "Slack",
  "WhatsApp",
  "Push Notifications",
  "Security",
] as const;

const WHATSAPP_PHONE_REGEX = /^\+?[1-9]\d{7,14}$/;

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : getApiErrorMessage(err);
}

function initialsOf(name: string) {
  const parts = name.trim().split(/\s+/);
  return parts.length === 1 ? parts[0].slice(0, 2).toUpperCase() : (parts[0][0] + parts[1][0]).toUpperCase();
}

export default function Settings() {
  const { push } = useToast();
  const { user, refetchUser } = useAuth();
  const [tab, setTab] = React.useState<(typeof TABS)[number]>("Profile");
  const [searchParams, setSearchParams] = useSearchParams();

  const [name, setName] = React.useState(user?.name ?? "");
  const [email, setEmail] = React.useState(user?.email ?? "");
  const [timezone, setTimezone] = React.useState(user?.timezone ?? "UTC");
  React.useEffect(() => {
    if (user) {
      setName(user.name);
      setEmail(user.email);
      setTimezone(user.timezone);
    }
  }, [user]);

  const saveProfile = useMutation({
    mutationFn: () => usersApi.update(user!.id, { name, email, timezone }),
    onSuccess: async () => {
      await refetchUser();
      push("success", "Profile updated");
    },
    onError: (err) => push("error", "Couldn't save profile", getApiErrorMessage(err)),
  });

  const [password, setPassword] = React.useState("");
  const savePassword = useMutation({
    mutationFn: () => usersApi.updatePassword(user!.id, password),
    onSuccess: () => {
      push("success", "Password updated");
      setPassword("");
    },
    onError: (err) => push("error", "Couldn't update password", getApiErrorMessage(err)),
  });

  const { data: googleStatus, isLoading: googleStatusLoading, refetch: refetchGoogle } = useQuery({
    queryKey: ["google-status"],
    queryFn: googleApi.status,
  });
  const disconnectGoogle = useMutation({
    mutationFn: googleApi.disconnect,
    onSuccess: () => {
      push("success", "Google Calendar disconnected");
      refetchGoogle();
    },
    onError: (err) => push("error", "Couldn't disconnect", getApiErrorMessage(err)),
  });

  React.useEffect(() => {
    const googleResult = searchParams.get("google");
    if (!googleResult) return;

    if (googleResult === "connected") {
      push("success", "Google Calendar connected");
      refetchGoogle();
    } else if (googleResult === "error") {
      push("error", "Couldn't connect Google Calendar", "Please try again.");
    }

    const next = new URLSearchParams(searchParams);
    next.delete("google");
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const { data: outlookStatus, isLoading: outlookStatusLoading, refetch: refetchOutlook } = useQuery({
    queryKey: ["outlook-status"],
    queryFn: outlookApi.status,
  });
  const connectOutlook = useMutation({
    mutationFn: outlookApi.connect,
    onSuccess: (data) => {
      window.location.href = data.authorization_url;
    },
    onError: (err) => push("error", "Couldn't connect Outlook", getApiErrorMessage(err)),
  });
  const disconnectOutlook = useMutation({
    mutationFn: outlookApi.disconnect,
    onSuccess: () => {
      push("success", "Outlook Calendar disconnected");
      refetchOutlook();
    },
    onError: (err) => push("error", "Couldn't disconnect", getApiErrorMessage(err)),
  });

  React.useEffect(() => {
    const outlookResult = searchParams.get("outlook");
    if (!outlookResult) return;

    if (outlookResult === "connected") {
      push("success", "Outlook Calendar connected");
      refetchOutlook();
      // Microsoft Teams availability mirrors Outlook's connection
      // state, so it changes here too.
      refetchTeams();
    } else if (outlookResult === "error") {
      push("error", "Couldn't connect Outlook Calendar", "Please try again.");
    }

    const next = new URLSearchParams(searchParams);
    next.delete("outlook");
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const { data: zoomStatus, isLoading: zoomStatusLoading, refetch: refetchZoom } = useQuery({
    queryKey: ["zoom-status"],
    queryFn: zoomApi.status,
  });
  const connectZoom = useMutation({
    mutationFn: zoomApi.connect,
    onSuccess: (data) => {
      window.location.href = data.authorization_url;
    },
    onError: (err) => push("error", "Couldn't connect Zoom", getApiErrorMessage(err)),
  });
  const disconnectZoom = useMutation({
    mutationFn: zoomApi.disconnect,
    onSuccess: () => {
      push("success", "Zoom disconnected");
      refetchZoom();
    },
    onError: (err) => push("error", "Couldn't disconnect", getApiErrorMessage(err)),
  });

  React.useEffect(() => {
    const zoomResult = searchParams.get("zoom");
    if (!zoomResult) return;

    if (zoomResult === "connected") {
      push("success", "Zoom connected");
      refetchZoom();
    } else if (zoomResult === "error") {
      push("error", "Couldn't connect Zoom", "Please try again.");
    }

    const next = new URLSearchParams(searchParams);
    next.delete("zoom");
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // Microsoft Teams Integration V1: "connected" mirrors Outlook's own
  // connection state (see api/teams_routes.py) - there is no separate
  // Teams connect/disconnect flow, so unlike the tabs above there's no
  // mutation or OAuth-callback effect here, just a status query.
  const { data: teamsStatus, isLoading: teamsStatusLoading, refetch: refetchTeams } = useQuery({
    queryKey: ["teams-status"],
    queryFn: teamsApi.status,
  });

  const { data: slackStatus, isLoading: slackStatusLoading, refetch: refetchSlack } = useQuery({
    queryKey: ["slack-status"],
    queryFn: slackApi.status,
  });
  const connectSlack = useMutation({
    mutationFn: slackApi.connect,
    onSuccess: (data) => {
      window.location.href = data.authorization_url;
    },
    onError: (err) => push("error", "Couldn't connect Slack", getApiErrorMessage(err)),
  });
  const disconnectSlack = useMutation({
    mutationFn: slackApi.disconnect,
    onSuccess: () => {
      push("success", "Slack disconnected");
      refetchSlack();
    },
    onError: (err) => push("error", "Couldn't disconnect", getApiErrorMessage(err)),
  });
  const testSlack = useMutation({
    mutationFn: slackApi.sendTest,
    onSuccess: () => push("success", "Test notification sent", "Check your Slack direct messages."),
    onError: (err) => push("error", "Couldn't send test notification", getApiErrorMessage(err)),
  });

  React.useEffect(() => {
    const slackResult = searchParams.get("slack");
    if (!slackResult) return;

    if (slackResult === "connected") {
      push("success", "Slack connected");
      refetchSlack();
    } else if (slackResult === "error") {
      push("error", "Couldn't connect Slack", "Please try again.");
    }

    const next = new URLSearchParams(searchParams);
    next.delete("slack");
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const {
    data: whatsappStatus,
    isLoading: whatsappStatusLoading,
    refetch: refetchWhatsapp,
  } = useQuery({
    queryKey: ["whatsapp-status"],
    queryFn: whatsappApi.status,
  });
  const [whatsappPhone, setWhatsappPhone] = React.useState("");
  const [whatsappPhoneError, setWhatsappPhoneError] = React.useState<string | undefined>(undefined);
  React.useEffect(() => {
    if (whatsappStatus) setWhatsappPhone(whatsappStatus.phone_number ?? "");
  }, [whatsappStatus]);

  const saveWhatsapp = useMutation({
    mutationFn: (phoneNumber: string) =>
      whatsappApi.updateSettings({ phone_number: phoneNumber, is_enabled: true }),
    onSuccess: () => {
      push("success", "WhatsApp number saved");
      refetchWhatsapp();
    },
    onError: (err) => push("error", "Couldn't save WhatsApp settings", getApiErrorMessage(err)),
  });
  const testWhatsapp = useMutation({
    mutationFn: whatsappApi.sendTest,
    onSuccess: () => push("success", "Test notification sent", "Check your WhatsApp messages."),
    onError: (err) => push("error", "Couldn't send test notification", getApiErrorMessage(err)),
  });

  const handleSaveWhatsapp = () => {
    const trimmed = whatsappPhone.trim();
    if (!trimmed) {
      setWhatsappPhoneError("Phone number is required.");
      return;
    }
    if (!WHATSAPP_PHONE_REGEX.test(trimmed)) {
      setWhatsappPhoneError("Enter a valid phone number in international format, e.g. +14155552671.");
      return;
    }
    setWhatsappPhoneError(undefined);
    saveWhatsapp.mutate(trimmed);
  };

  const {
    isSupported: pushSupported,
    permission: pushPermission,
    subscribed: pushSubscribed,
    checking: pushChecking,
    subscribe: subscribeBrowserPush,
    unsubscribe: unsubscribeBrowserPush,
  } = usePushNotifications();
  const { data: pushStatus, isLoading: pushStatusLoading, refetch: refetchPush } = useQuery({
    queryKey: ["push-status"],
    queryFn: pushApi.status,
  });
  const subscribePush = useMutation({
    mutationFn: subscribeBrowserPush,
    onSuccess: () => {
      push("success", "Push notifications enabled");
      refetchPush();
    },
    onError: (err) => push("error", "Couldn't enable push notifications", errorMessage(err)),
  });
  const unsubscribePush = useMutation({
    mutationFn: unsubscribeBrowserPush,
    onSuccess: () => {
      push("success", "Push notifications disabled");
      refetchPush();
    },
    onError: (err) => push("error", "Couldn't disable push notifications", errorMessage(err)),
  });
  const testPush = useMutation({
    mutationFn: pushApi.sendTest,
    onSuccess: () => push("success", "Test notification sent"),
    onError: (err) => push("error", "Couldn't send test notification", getApiErrorMessage(err)),
  });

  if (!user) return null;

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6">
        <h1 className="text-[28px] font-bold text-slate-900">Account settings</h1>
        <p className="mt-1 text-sm text-slate-500">Manage your profile, integrations, and security.</p>
      </div>

      <div className="mb-6 flex items-center gap-3">
        <Avatar initials={initialsOf(user.name)} size={56} colorClass="bg-brand-100 text-brand-700" />
        <div>
          <p className="font-semibold text-slate-900">{user.name}</p>
          <p className="text-sm text-slate-500">{user.email}</p>
        </div>
      </div>

      <div className="mb-6 flex gap-1 border-b border-slate-200">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${
              tab === t ? "border-brand-600 font-medium text-brand-700" : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Profile" && (
        <Card className="space-y-4 p-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-700">Full name</label>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-700">Email</label>
              <Input value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-700">Timezone</label>
            <Select value={timezone} onChange={(e) => setTimezone(e.target.value)}>
              <option value="UTC">UTC</option>
              <option value="Asia/Kolkata">Asia/Kolkata (UTC+5:30)</option>
              <option value="America/New_York">America/New_York (UTC-5:00)</option>
              <option value="Europe/London">Europe/London (UTC+0:00)</option>
            </Select>
          </div>
          <div className="flex justify-end">
            <Button onClick={() => saveProfile.mutate()} loading={saveProfile.isPending}>
              Save changes
            </Button>
          </div>
        </Card>
      )}

      {tab === "Google Calendar" && (
        <Card className="p-6">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100">
              <Calendar className="h-4 w-4 text-slate-600" />
            </div>
            <div className="flex-1">
              <p className="font-medium text-slate-900">Google Calendar</p>
              <p className="mt-0.5 flex items-center gap-1 text-xs text-slate-500">
                {googleStatusLoading ? (
                  "Checking connection..."
                ) : googleStatus?.connected ? (
                  <>
                    <CheckCircle2 className="h-3 w-3 text-emerald-600" /> Connected
                  </>
                ) : (
                  <>
                    <MailWarning className="h-3 w-3 text-amber-600" /> Not connected
                  </>
                )}
              </p>
            </div>
            {googleStatus?.connected ? (
              <Button
                variant="danger"
                onClick={() => disconnectGoogle.mutate()}
                loading={disconnectGoogle.isPending}
              >
                Disconnect
              </Button>
            ) : (
              <Button
                disabled={googleStatusLoading}
                onClick={() => (window.location.href = googleApi.connectRedirectUrl())}
              >
                Connect Google
              </Button>
            )}
          </div>
        </Card>
      )}

      {tab === "Outlook Calendar" && (
        <Card className="p-6">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100">
              <Calendar className="h-4 w-4 text-slate-600" />
            </div>
            <div className="flex-1">
              <p className="font-medium text-slate-900">Outlook Calendar</p>
              <p className="mt-0.5 flex items-center gap-1 text-xs text-slate-500">
                {outlookStatusLoading ? (
                  "Checking connection..."
                ) : outlookStatus?.connected ? (
                  <>
                    <CheckCircle2 className="h-3 w-3 text-emerald-600" /> Connected
                  </>
                ) : (
                  <>
                    <MailWarning className="h-3 w-3 text-amber-600" /> Not connected
                  </>
                )}
              </p>
            </div>
            {outlookStatus?.connected ? (
              <Button
                variant="danger"
                onClick={() => disconnectOutlook.mutate()}
                loading={disconnectOutlook.isPending}
              >
                Disconnect
              </Button>
            ) : (
              <Button
                disabled={outlookStatusLoading}
                onClick={() => connectOutlook.mutate()}
                loading={connectOutlook.isPending}
              >
                Connect Outlook
              </Button>
            )}
          </div>
        </Card>
      )}

      {tab === "Zoom Meetings" && (
        <Card className="p-6">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100">
              <Video className="h-4 w-4 text-slate-600" />
            </div>
            <div className="flex-1">
              <p className="font-medium text-slate-900">Zoom Meetings</p>
              <p className="mt-0.5 flex items-center gap-1 text-xs text-slate-500">
                {zoomStatusLoading ? (
                  "Checking connection..."
                ) : zoomStatus?.connected ? (
                  <>
                    <CheckCircle2 className="h-3 w-3 text-emerald-600" /> Connected
                  </>
                ) : (
                  <>
                    <MailWarning className="h-3 w-3 text-amber-600" /> Not connected
                  </>
                )}
              </p>
            </div>
            {zoomStatus?.connected ? (
              <Button
                variant="danger"
                onClick={() => disconnectZoom.mutate()}
                loading={disconnectZoom.isPending}
              >
                Disconnect
              </Button>
            ) : (
              <Button
                disabled={zoomStatusLoading}
                onClick={() => connectZoom.mutate()}
                loading={connectZoom.isPending}
              >
                Connect Zoom
              </Button>
            )}
          </div>
        </Card>
      )}

      {tab === "Microsoft Teams" && (
        <Card className="p-6">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100">
              <Users className="h-4 w-4 text-slate-600" />
            </div>
            <div className="flex-1">
              <p className="font-medium text-slate-900">Microsoft Teams</p>
              <p className="mt-0.5 flex items-center gap-1 text-xs text-slate-500">
                {teamsStatusLoading ? (
                  "Checking connection..."
                ) : teamsStatus?.connected ? (
                  <>
                    <CheckCircle2 className="h-3 w-3 text-emerald-600" /> Connected
                  </>
                ) : (
                  <>
                    <MailWarning className="h-3 w-3 text-amber-600" /> Not connected
                  </>
                )}
              </p>
              <p className="mt-1 text-xs text-slate-400">
                Teams meetings are added to your synced Outlook Calendar events - there&apos;s nothing separate to
                connect here.
              </p>
            </div>
            {!teamsStatus?.connected && (
              <Button disabled={teamsStatusLoading} onClick={() => setTab("Outlook Calendar")}>
                Connect Outlook
              </Button>
            )}
          </div>
        </Card>
      )}

      {tab === "Slack" && (
        <Card className="p-6">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100">
              <Hash className="h-4 w-4 text-slate-600" />
            </div>
            <div className="flex-1">
              <p className="font-medium text-slate-900">Slack</p>
              <p className="mt-0.5 flex items-center gap-1 text-xs text-slate-500">
                {slackStatusLoading ? (
                  "Checking connection..."
                ) : slackStatus?.connected ? (
                  <>
                    <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                    {slackStatus.team_name ? `Connected to ${slackStatus.team_name}` : "Connected"}
                  </>
                ) : (
                  <>
                    <MailWarning className="h-3 w-3 text-amber-600" /> Not connected
                  </>
                )}
              </p>
            </div>
            {slackStatus?.connected ? (
              <Button
                variant="danger"
                onClick={() => disconnectSlack.mutate()}
                loading={disconnectSlack.isPending}
              >
                Disconnect
              </Button>
            ) : (
              <Button
                disabled={slackStatusLoading}
                onClick={() => connectSlack.mutate()}
                loading={connectSlack.isPending}
              >
                Connect Slack
              </Button>
            )}
          </div>
          {slackStatus?.connected && (
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
              <p className="text-xs text-slate-500">
                Send yourself a Slack direct message to confirm notifications are working.
              </p>
              <Button
                variant="secondary"
                onClick={() => testSlack.mutate()}
                loading={testSlack.isPending}
              >
                Send Test Notification
              </Button>
            </div>
          )}
        </Card>
      )}

      {tab === "WhatsApp" && (
        <Card className="space-y-4 p-6">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100">
              <MessageCircle className="h-4 w-4 text-slate-600" />
            </div>
            <div className="flex-1">
              <p className="font-medium text-slate-900">WhatsApp</p>
              <p className="mt-0.5 flex items-center gap-1 text-xs text-slate-500">
                {whatsappStatusLoading ? (
                  "Checking status..."
                ) : whatsappStatus?.enabled && whatsappStatus.phone_number ? (
                  <>
                    <CheckCircle2 className="h-3 w-3 text-emerald-600" /> Configured
                  </>
                ) : (
                  <>
                    <MailWarning className="h-3 w-3 text-amber-600" /> Not configured
                  </>
                )}
              </p>
            </div>
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-700">Recipient phone number</label>
            <Input
              value={whatsappPhone}
              onChange={(e) => {
                setWhatsappPhone(e.target.value);
                setWhatsappPhoneError(undefined);
              }}
              placeholder="+14155552671"
              error={whatsappPhoneError}
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button
              variant="secondary"
              disabled={!whatsappStatus?.enabled || !whatsappStatus.phone_number}
              onClick={() => testWhatsapp.mutate()}
              loading={testWhatsapp.isPending}
            >
              Send Test Notification
            </Button>
            <Button onClick={handleSaveWhatsapp} loading={saveWhatsapp.isPending}>
              Save changes
            </Button>
          </div>
        </Card>
      )}

      {tab === "Push Notifications" && (
        <Card className="p-6">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100">
              <Bell className="h-4 w-4 text-slate-600" />
            </div>
            <div className="flex-1">
              <p className="font-medium text-slate-900">Push Notifications</p>
              <p className="mt-0.5 flex items-center gap-1 text-xs text-slate-500">
                {!pushSupported ? (
                  <>
                    <MailWarning className="h-3 w-3 text-amber-600" /> Not supported in this browser
                  </>
                ) : pushChecking ? (
                  "Checking subscription..."
                ) : pushSubscribed ? (
                  <>
                    <CheckCircle2 className="h-3 w-3 text-emerald-600" /> Subscribed on this browser
                  </>
                ) : (
                  <>
                    <MailWarning className="h-3 w-3 text-amber-600" /> Not subscribed on this browser
                  </>
                )}
              </p>
            </div>
            <Badge
              variant={
                pushPermission === "granted" ? "success" : pushPermission === "denied" ? "danger" : "neutral"
              }
            >
              Permission: {pushPermission}
            </Badge>
          </div>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
            <p className="text-xs text-slate-500">
              {pushStatusLoading
                ? "Checking your subscriptions..."
                : `${pushStatus?.subscription_count ?? 0} device(s) subscribed across your browsers.`}
            </p>
            <div className="flex gap-2">
              {pushSubscribed ? (
                <Button
                  variant="danger"
                  onClick={() => unsubscribePush.mutate()}
                  loading={unsubscribePush.isPending}
                >
                  Unsubscribe
                </Button>
              ) : (
                <Button
                  disabled={!pushSupported || pushChecking}
                  onClick={() => subscribePush.mutate()}
                  loading={subscribePush.isPending}
                >
                  Subscribe
                </Button>
              )}
              <Button
                variant="secondary"
                disabled={!pushStatus?.enabled}
                onClick={() => testPush.mutate()}
                loading={testPush.isPending}
              >
                Send Test Notification
              </Button>
            </div>
          </div>
        </Card>
      )}

      {tab === "Security" && (
        <Card className="space-y-4 p-6">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-700">New password</label>
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
          </div>
          <div className="flex justify-end">
            <Button
              disabled={password.length < 1}
              onClick={() => savePassword.mutate()}
              loading={savePassword.isPending}
            >
              Update password
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
