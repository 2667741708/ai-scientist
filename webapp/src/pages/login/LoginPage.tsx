import { ArrowRight, Brain, Eye, EyeOff } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../features/auth/auth-context";
import { AuthApiError, fetchRecoveryChallenge, resetPasswordWithRecovery, storeAuthToken } from "../../lib/api/auth";
import { classNames, getSafeErrorMessage } from "../../lib/formatters/workbench";

type LoginMode = "researcher" | "register" | "admin" | "recovery";

const modeCopy: Record<LoginMode, { title: string; description: string; action: string; helper: string }> = {
  researcher: {
    title: "登录到开放共研",
    description: "使用课题组账号进入科研工作台。",
    action: "登录",
    helper: "继续处理论文资料、研究任务和产出草稿。",
  },
  register: {
    title: "创建研究员账号",
    description: "为个人研究任务保留工作区和产出记录。",
    action: "创建账号",
    helper: "注册后默认使用研究员角色。密保问题可选，但建议填写用于自助找回密码。",
  },
  admin: {
    title: "管理员登录",
    description: "用于运行准备和账号管理。",
    action: "进入控制面",
    helper: "仅限管理员角色账号。",
  },
  recovery: {
    title: "找回密码",
    description: "通过注册时设置的密保问题重置密码。",
    action: "查找密保问题",
    helper: "未设置密保的账号需要联系管理员在后台重置临时密码。",
  },
};

const loginModes: Array<{ id: Extract<LoginMode, "researcher" | "register">; label: string }> = [
  { id: "researcher", label: "研究员" },
  { id: "register", label: "注册" },
];

const authFeedbackByCode: Record<string, string> = {
  "auth.register.account_exists": "这个邮箱已经注册过。请切换到“研究员”登录，或换一个邮箱创建账号。",
  "auth.register.invalid_email": "邮箱格式不正确，请检查后再试。",
  "auth.register.weak_password": "密码至少需要 8 个字符，请换一个更长的密码。",
  "auth.login.invalid_credentials": "邮箱或密码不正确。",
  "auth.login.invalid_email": "邮箱格式不正确，请检查后再试。",
  "auth.login.account_disabled": "账号已停用，请联系管理员恢复访问。",
  "auth.recovery.invalid_email": "邮箱格式不正确，请检查后再试。",
  "auth.recovery.invalid_answer": "密保答案不正确，请检查后再试。",
  "auth.recovery.unavailable": "该账号不能通过密保自助找回，请联系管理员重置临时密码。",
};

const LOGIN_EMAIL_STORAGE_KEY = "open_coscientist_login_email";
const LOGIN_PASSWORD_STORAGE_KEY = "open_coscientist_login_password";

function getAuthFeedback(error: unknown, fallback: string) {
  if (error instanceof AuthApiError) {
    return authFeedbackByCode[error.code] || getSafeErrorMessage(error, fallback);
  }
  return getSafeErrorMessage(error, fallback);
}

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { signIn, register, refreshUser } = useAuth();
  const [mode, setMode] = useState<LoginMode>("researcher");
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [recoveryQuestionInput, setRecoveryQuestionInput] = useState("");
  const [recoveryChallengeQuestion, setRecoveryChallengeQuestion] = useState("");
  const [recoveryAnswer, setRecoveryAnswer] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberEmail, setRememberEmail] = useState(true);
  const [rememberPassword, setRememberPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const [noticeTone, setNoticeTone] = useState<"error" | "success">("error");

  const redirectTo = useMemo(() => {
    const state = location.state as { redirectTo?: string } | null;
    const target = state?.redirectTo || "/home";
    if (!target.startsWith("/") || target === "/login") return "/home";
    return target;
  }, [location.state]);

  const copy = modeCopy[mode];
  const panelId = `login-panel-${mode}`;
  const panelLabelId = mode === "admin" || mode === "recovery" ? "login-title" : `login-tab-${mode}`;
  const submitAction = mode === "recovery" && recoveryChallengeQuestion ? "重置密码" : copy.action;
  const canRememberPassword = mode === "researcher" || mode === "admin";

  const clearRememberedPassword = () => {
    if (typeof localStorage !== "undefined") {
      localStorage.removeItem(LOGIN_PASSWORD_STORAGE_KEY);
    }
  };

  const persistLoginPreferences = (options: { includePassword: boolean }) => {
    if (typeof localStorage === "undefined") return;
    const normalizedEmail = email.trim();
    if (rememberEmail) {
      localStorage.setItem(LOGIN_EMAIL_STORAGE_KEY, normalizedEmail);
    } else {
      localStorage.removeItem(LOGIN_EMAIL_STORAGE_KEY);
    }

    if (options.includePassword && rememberPassword) {
      localStorage.setItem(LOGIN_PASSWORD_STORAGE_KEY, password);
    } else {
      localStorage.removeItem(LOGIN_PASSWORD_STORAGE_KEY);
    }
  };

  const switchMode = (nextMode: LoginMode) => {
    setMode(nextMode);
    setNotice("");
    setNoticeTone("error");
    setRecoveryChallengeQuestion("");
    setRecoveryAnswer("");
    if (nextMode !== "register") {
      setRecoveryQuestionInput("");
    }
    if (nextMode === "recovery" || nextMode === "register") {
      setPassword("");
    }
  };

  const handleRememberEmailChange = (checked: boolean) => {
    setRememberEmail(checked);
    if (!checked) {
      setRememberPassword(false);
      if (typeof localStorage !== "undefined") {
        localStorage.removeItem(LOGIN_EMAIL_STORAGE_KEY);
      }
      clearRememberedPassword();
    }
  };

  const handleRememberPasswordChange = (checked: boolean) => {
    setRememberPassword(checked);
    if (checked) {
      setRememberEmail(true);
    } else {
      clearRememberedPassword();
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setNotice("");
    setNoticeTone("error");
    setLoading(true);
    try {
      if (mode === "recovery") {
        if (!recoveryChallengeQuestion) {
          const challenge = await fetchRecoveryChallenge({ email });
          if (challenge.available && challenge.question) {
            setRecoveryChallengeQuestion(challenge.question);
            setNotice(challenge.message || "请回答密保问题并设置新密码。");
            setNoticeTone("success");
          } else {
            setNotice(challenge.message || "该账号不能通过密保自助找回，请联系管理员重置临时密码。");
          }
          return;
        }

        const session = await resetPasswordWithRecovery({
          email,
          answer: recoveryAnswer,
          new_password: password,
        });
        storeAuthToken(session.access_token);
        await refreshUser();
        persistLoginPreferences({ includePassword: false });
        navigate(redirectTo.startsWith("/admin") ? "/home" : redirectTo, { replace: true });
        return;
      }

      const user =
        mode === "register"
          ? await register({
              email,
              password,
              display_name: displayName,
              recovery_question: recoveryQuestionInput,
              recovery_answer: recoveryAnswer,
            })
          : await signIn({ email, password });
      persistLoginPreferences({ includePassword: mode !== "register" && canRememberPassword });
      const target = user.role === "admin" ? (redirectTo.startsWith("/admin") ? redirectTo : "/admin") : redirectTo.startsWith("/admin") ? "/home" : redirectTo;
      navigate(target, { replace: true });
    } catch (error) {
      const fallback =
        mode === "register" ? "注册失败，请检查账号信息。" : mode === "recovery" ? "找回密码失败，请检查账号和密保答案。" : "登录失败，请检查账号和密码。";
      setNotice(getAuthFeedback(error, fallback));
      setNoticeTone("error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (typeof localStorage !== "undefined") {
      const savedEmail = localStorage.getItem(LOGIN_EMAIL_STORAGE_KEY) || "";
      const savedPassword = localStorage.getItem(LOGIN_PASSWORD_STORAGE_KEY) || "";
      setEmail(savedEmail);
      if (savedPassword) {
        setPassword(savedPassword);
        setRememberEmail(true);
        setRememberPassword(true);
      }
    }
  }, []);

  return (
    <main className="login-shell">
      <section className="login-card" aria-labelledby="login-title">
        <div className="login-brand">
          <div className="brand-mark">
            <Brain size={20} />
          </div>
          <div>
            <strong>开放共研</strong>
            <span>实时文献支撑科研工作台</span>
          </div>
        </div>

        <div className="login-copy">
          <h1 id="login-title">{copy.title}</h1>
          <p>{copy.description}</p>
        </div>

        {mode === "admin" || mode === "recovery" ? (
          <div className="login-admin-mode" role="status">
            <span>{mode === "admin" ? "管理员入口" : "密码找回"}</span>
            <button type="button" className="forgot-link" disabled={loading} onClick={() => switchMode("researcher")}>
              返回研究员登录
            </button>
          </div>
        ) : (
          <div className="login-mode-tabs" role="tablist" aria-label="登录方式">
            {loginModes.map((item) => {
              const selected = mode === item.id;
              return (
                <button
                  type="button"
                  role="tab"
                  id={`login-tab-${item.id}`}
                  aria-selected={selected}
                  aria-controls={`login-panel-${item.id}`}
                  tabIndex={selected ? 0 : -1}
                  disabled={loading}
                  className={classNames(selected && "selected")}
                  onClick={() => switchMode(item.id)}
                  key={item.id}
                >
                  {item.label}
                </button>
              );
            })}
          </div>
        )}

        <form
          className="login-form"
          id={panelId}
          role="tabpanel"
          aria-labelledby={panelLabelId}
          aria-describedby={notice ? "login-form-error" : "login-form-helper"}
          onSubmit={handleSubmit}
        >
          <p className="login-mode-helper" id="login-form-helper">
            {copy.helper}
          </p>
          {mode === "register" ? (
            <label className="field-stack" htmlFor="login-display-name">
              <span>姓名或课题组内称呼</span>
              <input
                id="login-display-name"
                name="displayName"
                type="text"
                autoComplete="name"
                placeholder="例如：王同学"
                value={displayName}
                disabled={loading}
                onChange={(event) => setDisplayName(event.target.value)}
              />
            </label>
          ) : null}

          <label className="field-stack" htmlFor="login-email">
            <span>{mode === "admin" ? "管理员账号或邮箱" : "邮箱"}</span>
            <input
              id="login-email"
              name="email"
              type={mode === "admin" ? "text" : "email"}
              autoComplete="username"
              placeholder={mode === "admin" ? "admin 或管理员邮箱" : "researcher@example.com"}
              required
              disabled={loading}
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                if (mode === "recovery") {
                  setRecoveryChallengeQuestion("");
                  setRecoveryAnswer("");
                  setNotice("");
                }
              }}
              aria-invalid={noticeTone === "error" && Boolean(notice)}
              aria-describedby={notice ? "login-form-error" : undefined}
            />
          </label>

          {mode === "register" ? (
            <>
              <label className="field-stack" htmlFor="login-recovery-question">
                <span>密保问题（可选）</span>
                <input
                  id="login-recovery-question"
                  name="recoveryQuestion"
                  type="text"
                  placeholder="例如：你的第一篇论文主题是什么？"
                  value={recoveryQuestionInput}
                  disabled={loading}
                  onChange={(event) => setRecoveryQuestionInput(event.target.value)}
                />
              </label>
              <label className="field-stack" htmlFor="login-recovery-answer">
                <span>密保答案（可选）</span>
                <input
                  id="login-recovery-answer"
                  name="recoveryAnswer"
                  type="password"
                  autoComplete="off"
                  placeholder="用于忘记密码时自助重置"
                  value={recoveryAnswer}
                  disabled={loading}
                  onChange={(event) => setRecoveryAnswer(event.target.value)}
                />
              </label>
            </>
          ) : null}

          {mode === "recovery" && recoveryChallengeQuestion ? (
            <>
              <div className="recovery-question-panel" role="status">
                <span>密保问题</span>
                <strong>{recoveryChallengeQuestion}</strong>
              </div>
              <label className="field-stack" htmlFor="login-recovery-answer-reset">
                <span>密保答案</span>
                <input
                  id="login-recovery-answer-reset"
                  name="recoveryAnswer"
                  type="password"
                  autoComplete="off"
                  required
                  value={recoveryAnswer}
                  disabled={loading}
                  onChange={(event) => setRecoveryAnswer(event.target.value)}
                />
              </label>
            </>
          ) : null}

          {mode !== "recovery" || recoveryChallengeQuestion ? (
            <label className="field-stack" htmlFor="login-password">
              <span>{mode === "recovery" ? "新密码" : "密码"}</span>
              <div className="password-field">
                <input
                  id="login-password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete={mode === "register" || mode === "recovery" ? "new-password" : "current-password"}
                  placeholder={mode === "register" || mode === "recovery" ? "至少 8 个字符" : "请输入密码"}
                  required
                  minLength={mode === "register" || mode === "recovery" ? 8 : undefined}
                  disabled={loading}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  aria-invalid={noticeTone === "error" && Boolean(notice)}
                  aria-describedby={notice ? "login-form-error" : undefined}
                />
                <button
                  className="password-toggle"
                  type="button"
                  aria-label={showPassword ? "隐藏密码" : "显示密码"}
                  disabled={loading}
                  onClick={() => setShowPassword((value) => !value)}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </label>
          ) : null}

          <div className="login-row-actions">
            {mode === "recovery" ? (
              <span className="login-mode-helper">密保答案不会明文保存；管理员也只能重置密码。</span>
            ) : (
              <div className="remember-controls">
                <label className="remember-control">
                  <input type="checkbox" checked={rememberEmail} disabled={loading} onChange={(event) => handleRememberEmailChange(event.target.checked)} />
                  <span>记住邮箱</span>
                </label>
                {canRememberPassword ? (
                  <label className="remember-control">
                    <input type="checkbox" checked={rememberPassword} disabled={loading} onChange={(event) => handleRememberPasswordChange(event.target.checked)} />
                    <span>记住密码</span>
                  </label>
                ) : null}
              </div>
            )}
            <div className="login-inline-actions">
              {mode === "register" ? (
                <button type="button" className="forgot-link" disabled={loading} onClick={() => switchMode("researcher")}>
                  已有账号
                </button>
              ) : mode === "recovery" ? (
                <button type="button" className="forgot-link" disabled={loading} onClick={() => switchMode("researcher")}>
                  返回登录
                </button>
              ) : (
                <>
                  <button type="button" className="forgot-link" disabled={loading} onClick={() => switchMode("recovery")}>
                    忘记密码
                  </button>
                  <button type="button" className="forgot-link" disabled={loading} onClick={() => switchMode("register")}>
                    创建研究员账号
                  </button>
                </>
              )}
            </div>
          </div>

          {notice ? (
            <p className={classNames("control-feedback", noticeTone)} id="login-form-error" role="alert">
              {notice}
            </p>
          ) : null}

          <button className={classNames("button-primary", "login-submit", loading && "is-loading")} type="submit" aria-busy={loading} disabled={loading}>
            {loading ? "正在验证" : submitAction}
            <ArrowRight size={16} />
          </button>
        </form>

        <div className="login-secondary">
          <span>{mode === "admin" ? "使用研究员账号？" : "管理员账号？"}</span>
          <button type="button" className="forgot-link" disabled={loading} onClick={() => switchMode(mode === "admin" ? "researcher" : "admin")}>
            {mode === "admin" ? "返回登录" : "管理员入口"}
          </button>
        </div>
      </section>
    </main>
  );
}
