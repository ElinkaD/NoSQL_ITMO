import { useEffect, useMemo, useState } from "react";

const CATEGORY_OPTIONS = ["meetup", "concert", "exhibition", "party", "other"];
const DEFAULT_BASE_URL = "/api";

const NAV_ITEMS = [
  { path: "/", label: "Auth" },
  { path: "/events", label: "Events" },
  { path: "/organizers", label: "Organizers" },
  { path: "/dashboard", label: "Dashboard" },
  { path: "/tech", label: "Tech" },
];

const initialRegister = {
  full_name: "",
  username: "",
  password: "",
};

const initialLogin = {
  username: "",
  password: "",
};

const initialEventFilters = {
  title: "",
  id: "",
  category: "",
  price_from: "",
  price_to: "",
  city: "",
  date_from: "",
  date_to: "",
  user: "",
  limit: "",
  offset: "",
};

const initialUserFilters = {
  id: "",
  name: "",
  limit: "",
  offset: "",
};

const initialEventForm = {
  title: "",
  address: "",
  started_at: "",
  finished_at: "",
  category: "",
  price: "",
  description: "",
  city: "",
};

const initialEditForm = {
  event_id: "",
  category: "",
  price: "",
  city: "",
  clear_city: false,
};

const initialTechLookup = {
  user_id: "",
  event_id: "",
};

function getCurrentPath() {
  if (typeof window === "undefined") {
    return "/";
  }

  const path = window.location.pathname || "/";
  return NAV_ITEMS.some((item) => item.path === path) ? path : "/";
}

function navigateTo(path, setRoute) {
  window.history.pushState({}, "", path);
  setRoute(path);
}

function toQueryString(values) {
  const params = new URLSearchParams();

  Object.entries(values).forEach(([key, value]) => {
    if (value !== "" && value !== undefined && value !== null) {
      params.set(key, String(value).trim());
    }
  });

  const query = params.toString();
  return query ? `?${query}` : "";
}

function formatHeaders(headers) {
  return Array.from(headers.entries()).reduce((accumulator, [key, value]) => {
    accumulator[key] = value;
    return accumulator;
  }, {});
}

function formatResponseBody(text) {
  if (!text) {
    return "<empty>";
  }

  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
}

function SectionIntro({ eyebrow, title, description, actions }) {
  return (
    <div className="section-intro">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      {actions ? <div className="section-actions">{actions}</div> : null}
    </div>
  );
}

function EventCard({ event, onOpen, onPrepareEdit, compact = false }) {
  return (
    <article className={`card event-card ${compact ? "compact-card" : ""}`}>
      <div className="card-top">
        <span className="pill pill-event">{event.category ?? "event"}</span>
        {onOpen ? (
          <button type="button" className="text-button" onClick={() => onOpen(event.id)}>
            Open card
          </button>
        ) : null}
      </div>
      <h3>{event.title}</h3>
      <p>{event.description ?? "No description yet."}</p>
      <dl className="meta-list">
        <div>
          <dt>City</dt>
          <dd>{event.location?.city ?? "Not set"}</dd>
        </div>
        <div>
          <dt>Address</dt>
          <dd>{event.location?.address ?? "Not set"}</dd>
        </div>
        <div>
          <dt>Started</dt>
          <dd>{event.started_at}</dd>
        </div>
        <div>
          <dt>Price</dt>
          <dd>{event.price ?? "Free"}</dd>
        </div>
      </dl>
      {onPrepareEdit ? (
        <div className="inline-actions">
          <button type="button" className="ghost-button" onClick={() => onPrepareEdit(event)}>
            Edit in dashboard
          </button>
        </div>
      ) : null}
    </article>
  );
}

function OrganizerCard({ user, onOpenProfile, onOpenEvents }) {
  return (
    <article className="card organizer-card">
      <div className="card-top">
        <span className="pill pill-user">organizer</span>
        <span className="muted-copy">@{user.username}</span>
      </div>
      <h3>{user.full_name}</h3>
      <div className="inline-actions">
        <button type="button" className="ghost-button" onClick={() => onOpenProfile(user.id)}>
          Open profile
        </button>
        <button type="button" className="ghost-button" onClick={() => onOpenEvents(user.id)}>
          Open events
        </button>
      </div>
    </article>
  );
}

function ResponseInspector({ response }) {
  if (!response) {
    return <div className="empty-state">The last API response will appear here.</div>;
  }

  return (
    <div className="response-card">
      <div className="card-top">
        <span className={`pill ${response.ok ? "pill-success" : "pill-danger"}`}>
          {response.status} {response.statusText}
        </span>
        <code>{response.method}</code>
      </div>
      <p className="muted-copy response-url">{response.url}</p>
      <div className="response-block">
        <h4>Headers</h4>
        <pre>{JSON.stringify(response.headers, null, 2)}</pre>
      </div>
      <div className="response-block">
        <h4>Body</h4>
        <pre>{response.body}</pre>
      </div>
    </div>
  );
}

export default function App() {
  const [route, setRoute] = useState(getCurrentPath);
  const [baseUrl, setBaseUrl] = useState(DEFAULT_BASE_URL);
  const [isBusy, setIsBusy] = useState(false);
  const [lastAction, setLastAction] = useState("No scenario started yet");
  const [lastResponse, setLastResponse] = useState(null);
  const [sessionState, setSessionState] = useState("unknown");
  const [health, setHealth] = useState(null);

  const [registerForm, setRegisterForm] = useState(initialRegister);
  const [loginForm, setLoginForm] = useState(initialLogin);
  const [eventFilters, setEventFilters] = useState(initialEventFilters);
  const [userFilters, setUserFilters] = useState(initialUserFilters);
  const [createEventForm, setCreateEventForm] = useState(initialEventForm);
  const [editForm, setEditForm] = useState(initialEditForm);
  const [techLookup, setTechLookup] = useState(initialTechLookup);

  const [currentUser, setCurrentUser] = useState({
    userId: "",
    username: "",
    fullName: "",
  });
  const [catalogEvents, setCatalogEvents] = useState([]);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [organizers, setOrganizers] = useState([]);
  const [selectedOrganizer, setSelectedOrganizer] = useState(null);
  const [selectedOrganizerEvents, setSelectedOrganizerEvents] = useState([]);
  const [myEvents, setMyEvents] = useState([]);

  useEffect(() => {
    const handlePopState = () => setRoute(getCurrentPath());
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const currentUserReady = Boolean(currentUser.userId);

  const sessionLabel = useMemo(() => {
    if (sessionState === "authenticated") return "Authenticated organizer";
    if (sessionState === "session") return "Anonymous session";
    if (sessionState === "anonymous") return "Guest mode";
    return "Unknown auth state";
  }, [sessionState]);

  const request = async ({ method, path, body, label, track = true }) => {
    const url = `${baseUrl.replace(/\/$/, "")}${path}`;
    const options = {
      method,
      credentials: "include",
      headers: {},
    };

    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }

    if (track) {
      setIsBusy(true);
      setLastAction(label);
    }

    try {
      const response = await fetch(url, options);
      const text = await response.text();
      let payload = null;

      if (text) {
        try {
          payload = JSON.parse(text);
        } catch {
          payload = null;
        }
      }

      if (track) {
        setLastResponse({
          ok: response.ok,
          status: response.status,
          statusText: response.statusText || "No status text",
          method,
          url,
          headers: formatHeaders(response.headers),
          body: formatResponseBody(text),
        });
      }

      if (response.status === 401) {
        setSessionState("anonymous");
      }

      if (track) {
        setIsBusy(false);
      }

      return { ok: response.ok, status: response.status, payload };
    } catch (error) {
      if (track) {
        setLastResponse({
          ok: false,
          status: "NETWORK",
          statusText: "Request failed",
          method,
          url,
          headers: {},
          body: error instanceof Error ? error.message : "Unknown error",
        });
        setIsBusy(false);
      }

      return { ok: false, status: "NETWORK", payload: null };
    }
  };

  const syncCurrentUserByUsername = async (username, fullName = "") => {
    if (!username) {
      return;
    }

    const result = await request({
      method: "GET",
      path: "/users",
      label: "Resolve organizer profile",
      track: false,
    });

    if (!result.ok) {
      return;
    }

    const exactUser = (result.payload?.users ?? []).find((user) => user.username === username);
    if (exactUser) {
      setCurrentUser({
        userId: exactUser.id,
        username: exactUser.username,
        fullName: exactUser.full_name,
      });
      setTechLookup((current) => ({ ...current, user_id: exactUser.id }));
      return;
    }

    setCurrentUser((current) => ({
      ...current,
      username,
      fullName,
    }));
  };

  const loadHealth = async () => {
    const result = await request({
      method: "GET",
      path: "/health",
      label: "Healthcheck",
    });

    if (result.ok) {
      setHealth(result.payload);
    }
  };

  const createAnonymousSession = async () => {
    const result = await request({
      method: "POST",
      path: "/session",
      label: "Create anonymous session",
    });

    if (result.ok) {
      setSessionState("session");
    }
  };

  const registerOrganizer = async () => {
    const result = await request({
      method: "POST",
      path: "/users",
      body: registerForm,
      label: "Register organizer",
    });

    if (result.ok) {
      setSessionState("authenticated");
      await syncCurrentUserByUsername(registerForm.username, registerForm.full_name);
      navigateTo("/dashboard", setRoute);
    }
  };

  const loginOrganizer = async () => {
    const result = await request({
      method: "POST",
      path: "/auth/login",
      body: loginForm,
      label: "Login organizer",
    });

    if (result.ok) {
      setSessionState("authenticated");
      await syncCurrentUserByUsername(loginForm.username);
      navigateTo("/dashboard", setRoute);
    }
  };

  const logoutOrganizer = async () => {
    const result = await request({
      method: "POST",
      path: "/auth/logout",
      label: "Logout organizer",
    });

    if (result.ok) {
      setSessionState("anonymous");
      setCurrentUser({ userId: "", username: "", fullName: "" });
      setMyEvents([]);
    }
  };

  const loadEventCatalog = async () => {
    const result = await request({
      method: "GET",
      path: `/events${toQueryString(eventFilters)}`,
      label: "Search all events",
    });

    if (result.ok) {
      setCatalogEvents(result.payload?.events ?? []);
      const firstEvent = result.payload?.events?.[0];
      if (firstEvent?.id) {
        setTechLookup((current) => ({ ...current, event_id: firstEvent.id }));
      }
    }
  };

  const openEventCard = async (eventId) => {
    if (!eventId) return;

    const result = await request({
      method: "GET",
      path: `/events/${eventId}`,
      label: "Open event card",
    });

    if (result.ok) {
      setSelectedEvent(result.payload);
      setTechLookup((current) => ({ ...current, event_id: eventId }));
    }
  };

  const loadOrganizers = async () => {
    const result = await request({
      method: "GET",
      path: `/users${toQueryString(userFilters)}`,
      label: "Load organizer directory",
    });

    if (result.ok) {
      setOrganizers(result.payload?.users ?? []);
    }
  };

  const openOrganizerProfile = async (userId) => {
    if (!userId) return;

    const result = await request({
      method: "GET",
      path: `/users/${userId}`,
      label: "Open organizer profile",
    });

    if (result.ok) {
      setSelectedOrganizer(result.payload);
      setTechLookup((current) => ({ ...current, user_id: userId }));
    }
  };

  const openOrganizerEvents = async (userId) => {
    if (!userId) return;

    const query = {
      title: eventFilters.title,
      id: eventFilters.id,
      category: eventFilters.category,
      price_from: eventFilters.price_from,
      price_to: eventFilters.price_to,
      city: eventFilters.city,
      date_from: eventFilters.date_from,
      date_to: eventFilters.date_to,
      limit: eventFilters.limit,
      offset: eventFilters.offset,
    };

    const result = await request({
      method: "GET",
      path: `/users/${userId}/events${toQueryString(query)}`,
      label: "Open organizer events",
    });

    if (result.ok) {
      setSelectedOrganizerEvents(result.payload?.events ?? []);
    }
  };

  const refreshMyProfile = async () => {
    if (currentUser.userId) {
      const result = await request({
        method: "GET",
        path: `/users/${currentUser.userId}`,
        label: "Refresh my profile",
      });

      if (result.ok) {
        setCurrentUser({
          userId: result.payload.id,
          username: result.payload.username,
          fullName: result.payload.full_name,
        });
      }
      return;
    }

    await syncCurrentUserByUsername(currentUser.username || loginForm.username || registerForm.username);
  };

  const loadMyEvents = async () => {
    if (!currentUser.userId) return;

    const result = await request({
      method: "GET",
      path: `/users/${currentUser.userId}/events`,
      label: "Load my organizer events",
    });

    if (result.ok) {
      setMyEvents(result.payload?.events ?? []);
    }
  };

  const createEvent = async () => {
    const body = {
      ...createEventForm,
      ...(createEventForm.price === "" ? {} : { price: Number(createEventForm.price) }),
    };

    if (body.price === undefined) {
      delete body.price;
    }

    const result = await request({
      method: "POST",
      path: "/events",
      body,
      label: "Create event from dashboard",
    });

    if (result.ok) {
      setSessionState("authenticated");
      const eventId = result.payload?.id ?? "";
      setEditForm((current) => ({ ...current, event_id: eventId || current.event_id }));
      setTechLookup((current) => ({ ...current, event_id: eventId || current.event_id }));
      await loadMyEvents();
      if (eventId) {
        await openEventCard(eventId);
      }
    }
  };

  const patchEvent = async () => {
    if (!editForm.event_id) return;

    const body = {};
    if (editForm.category) body.category = editForm.category;
    if (editForm.price !== "") body.price = Number(editForm.price);
    if (editForm.clear_city) {
      body.city = "";
    } else if (editForm.city !== "") {
      body.city = editForm.city;
    }

    const result = await request({
      method: "PATCH",
      path: `/events/${editForm.event_id}`,
      body,
      label: "Patch my event",
    });

    if (result.ok) {
      await loadMyEvents();
      await openEventCard(editForm.event_id);
    }
  };

  const prepareEventEditor = (event) => {
    setEditForm({
      event_id: event.id,
      category: event.category ?? "",
      price: event.price ?? "",
      city: event.location?.city ?? "",
      clear_city: false,
    });
    navigateTo("/dashboard", setRoute);
  };

  const runTechUserLookup = async () => {
    await openOrganizerProfile(techLookup.user_id);
  };

  const runTechEventLookup = async () => {
    await openEventCard(techLookup.event_id);
  };

  return (
    <div className="site-shell">
      <header className="topbar card shell-card">
        <div>
          <h1>EventHub</h1>
          <p className="hero-copy">Events, organizers and publishing flows.</p>
        </div>

        <div className="hero-status">
          <div className={`status-dot state-${sessionState}`} />
          <div>
            <strong>{sessionLabel}</strong>
            <p>{lastAction}</p>
          </div>
        </div>
      </header>

      <nav className="nav-row">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.path}
            type="button"
            className={`nav-pill ${route === item.path ? "nav-pill-active" : ""}`}
            onClick={() => navigateTo(item.path, setRoute)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      <main className="app-grid">
        <section className="page-column">
          {route === "/" && (
            <section className="card page-panel">
              <SectionIntro
                eyebrow="Page 1"
                title="Authorization"
                description="Полноценный сценарий входа и регистрации организатора, который ведет в кабинет."
                actions={
                  <>
                    <button type="button" className="ghost-button" onClick={loadHealth}>
                      GET /health
                    </button>
                    <button type="button" className="ghost-button" onClick={createAnonymousSession}>
                      POST /session
                    </button>
                  </>
                }
              />

              <div className="two-column-grid">
                <article className="card inner-card">
                  <div className="card-top">
                    <span className="pill pill-info">POST /users</span>
                    <span className="muted-copy">signup + auto login</span>
                  </div>
                  <h3>Create organizer account</h3>
                  <div className="form-grid">
                    <label className="field">
                      <span>Full name</span>
                      <input
                        value={registerForm.full_name}
                        onChange={(event) =>
                          setRegisterForm((current) => ({ ...current, full_name: event.target.value }))
                        }
                        placeholder="Elina Dusaeva"
                      />
                    </label>
                    <label className="field">
                      <span>Username</span>
                      <input
                        value={registerForm.username}
                        onChange={(event) =>
                          setRegisterForm((current) => ({ ...current, username: event.target.value }))
                        }
                        placeholder="elina"
                      />
                    </label>
                    <label className="field wide-field">
                      <span>Password</span>
                      <input
                        type="password"
                        value={registerForm.password}
                        onChange={(event) =>
                          setRegisterForm((current) => ({ ...current, password: event.target.value }))
                        }
                        placeholder="secret"
                      />
                    </label>
                  </div>
                  <button type="button" className="primary-button" onClick={registerOrganizer}>
                    Register and open dashboard
                  </button>
                </article>

                <article className="card inner-card">
                  <div className="card-top">
                    <span className="pill pill-info">POST /auth/login</span>
                    <span className="muted-copy">existing organizer</span>
                  </div>
                  <h3>Login form</h3>
                  <div className="form-grid">
                    <label className="field">
                      <span>Username</span>
                      <input
                        value={loginForm.username}
                        onChange={(event) =>
                          setLoginForm((current) => ({ ...current, username: event.target.value }))
                        }
                        placeholder="elina"
                      />
                    </label>
                    <label className="field">
                      <span>Password</span>
                      <input
                        type="password"
                        value={loginForm.password}
                        onChange={(event) =>
                          setLoginForm((current) => ({ ...current, password: event.target.value }))
                        }
                        placeholder="secret"
                      />
                    </label>
                  </div>
                  <div className="inline-actions">
                    <button type="button" className="primary-button" onClick={loginOrganizer}>
                      Login and open dashboard
                    </button>
                    <button type="button" className="ghost-button" onClick={logoutOrganizer}>
                      Logout
                    </button>
                  </div>

                  <div className="note-box">
                    <strong>Login scenario</strong>
                    <p>
                      После `204` фронт автоматически делает lookup профиля через `GET /users`,
                      чтобы получить `userId` и открыть кабинет организатора.
                    </p>
                  </div>
                </article>
              </div>
            </section>
          )}

          {route === "/events" && (
            <section className="card page-panel">
              <SectionIntro
                eyebrow="Page 2"
                title="All Events"
                description="Общая страница со всеми мероприятиями и фильтрами."
                actions={
                  <button type="button" className="primary-button" onClick={loadEventCatalog}>
                    Search events
                  </button>
                }
              />

              <div className="filter-strip">
                <div className="form-grid form-grid-3">
                  <label className="field">
                    <span>Title</span>
                    <input
                      value={eventFilters.title}
                      onChange={(event) => setEventFilters((current) => ({ ...current, title: event.target.value }))}
                      placeholder="Backend meetup"
                    />
                  </label>
                  <label className="field">
                    <span>Organizer username</span>
                    <input
                      value={eventFilters.user}
                      onChange={(event) => setEventFilters((current) => ({ ...current, user: event.target.value }))}
                      placeholder="elina"
                    />
                  </label>
                  <label className="field">
                    <span>Category</span>
                    <select
                      value={eventFilters.category}
                      onChange={(event) => setEventFilters((current) => ({ ...current, category: event.target.value }))}
                    >
                      <option value="">all</option>
                      {CATEGORY_OPTIONS.map((category) => (
                        <option key={category} value={category}>
                          {category}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span>City</span>
                    <input
                      value={eventFilters.city}
                      onChange={(event) => setEventFilters((current) => ({ ...current, city: event.target.value }))}
                      placeholder="Moscow"
                    />
                  </label>
                  <label className="field">
                    <span>Date from</span>
                    <input
                      value={eventFilters.date_from}
                      onChange={(event) =>
                        setEventFilters((current) => ({ ...current, date_from: event.target.value }))
                      }
                      placeholder="20260501"
                    />
                  </label>
                  <label className="field">
                    <span>Date to</span>
                    <input
                      value={eventFilters.date_to}
                      onChange={(event) =>
                        setEventFilters((current) => ({ ...current, date_to: event.target.value }))
                      }
                      placeholder="20260531"
                    />
                  </label>
                </div>
              </div>

              <div className="cards-grid">
                {catalogEvents.length === 0 ? (
                  <div className="empty-state">Run the search and event cards will appear here.</div>
                ) : (
                  catalogEvents.map((event) => (
                    <EventCard key={event.id} event={event} onOpen={openEventCard} />
                  ))
                )}
              </div>
            </section>
          )}

          {route === "/organizers" && (
            <section className="card page-panel">
              <SectionIntro
                eyebrow="Page 3"
                title="Profiles and Organizer Events"
                description="Отдельная страница для профилей организаторов и просмотра их мероприятий."
                actions={
                  <button type="button" className="primary-button" onClick={loadOrganizers}>
                    Load organizers
                  </button>
                }
              />

              <div className="filter-strip">
                <div className="form-grid">
                  <label className="field">
                    <span>Name</span>
                    <input
                      value={userFilters.name}
                      onChange={(event) => setUserFilters((current) => ({ ...current, name: event.target.value }))}
                      placeholder="Elina"
                    />
                  </label>
                  <label className="field">
                    <span>User ID</span>
                    <input
                      value={userFilters.id}
                      onChange={(event) => setUserFilters((current) => ({ ...current, id: event.target.value }))}
                      placeholder="ObjectId"
                    />
                  </label>
                  <label className="field">
                    <span>Limit</span>
                    <input
                      value={userFilters.limit}
                      onChange={(event) => setUserFilters((current) => ({ ...current, limit: event.target.value }))}
                      placeholder="10"
                    />
                  </label>
                  <label className="field">
                    <span>Offset</span>
                    <input
                      value={userFilters.offset}
                      onChange={(event) => setUserFilters((current) => ({ ...current, offset: event.target.value }))}
                      placeholder="0"
                    />
                  </label>
                </div>
              </div>

              <div className="split-layout">
                <div className="cards-grid compact-grid">
                  {organizers.length === 0 ? (
                    <div className="empty-state">Organizer cards will appear here.</div>
                  ) : (
                    organizers.map((user) => (
                      <OrganizerCard
                        key={user.id}
                        user={user}
                        onOpenProfile={openOrganizerProfile}
                        onOpenEvents={openOrganizerEvents}
                      />
                    ))
                  )}
                </div>

                <div className="detail-column">
                  <article className="card inner-card">
                    <div className="card-top">
                      <span className="pill pill-neutral">GET /users/{`{id}`}</span>
                    </div>
                    <h3>{selectedOrganizer?.full_name ?? "Organizer profile"}</h3>
                    <p>{selectedOrganizer ? `@${selectedOrganizer.username}` : "Select an organizer card."}</p>
                    {selectedOrganizer ? (
                      <dl className="meta-list">
                        <div>
                          <dt>User ID</dt>
                          <dd>{selectedOrganizer.id}</dd>
                        </div>
                        <div>
                          <dt>Username</dt>
                          <dd>{selectedOrganizer.username}</dd>
                        </div>
                      </dl>
                    ) : null}
                  </article>

                  <article className="card inner-card">
                    <div className="card-top">
                      <span className="pill pill-neutral">GET /users/{`{id}`}/events</span>
                    </div>
                    <h3>Organizer events</h3>
                    {selectedOrganizerEvents.length === 0 ? (
                      <div className="empty-state">Organizer events will appear here.</div>
                    ) : (
                      <div className="cards-grid compact-grid">
                        {selectedOrganizerEvents.map((event) => (
                          <EventCard key={event.id} event={event} onOpen={openEventCard} compact />
                        ))}
                      </div>
                    )}
                  </article>
                </div>
              </div>
            </section>
          )}

          {route === "/dashboard" && (
            <section className="card page-panel">
              <SectionIntro
                eyebrow="Page 4"
                title="Organizer Dashboard"
                description="Профильная страница организатора: создание события, мои события и редактирование."
                actions={
                  <>
                    <button type="button" className="ghost-button" onClick={refreshMyProfile}>
                      Refresh my profile
                    </button>
                    <button type="button" className="ghost-button" onClick={loadMyEvents}>
                      Load my events
                    </button>
                  </>
                }
              />

              {!currentUserReady ? (
                <div className="empty-state">
                  Login or register first. After that the dashboard resolves your organizer profile and enables
                  event creation/editing.
                </div>
              ) : (
                <>
                  <div className="dashboard-hero card inner-card">
                    <div>
                      <p className="eyebrow">Organizer Profile</p>
                      <h3>{currentUser.fullName || currentUser.username}</h3>
                      <p className="muted-copy">@{currentUser.username}</p>
                    </div>
                    <dl className="profile-stats">
                      <div>
                        <dt>User ID</dt>
                        <dd>{currentUser.userId}</dd>
                      </div>
                      <div>
                        <dt>Session</dt>
                        <dd>{sessionLabel}</dd>
                      </div>
                    </dl>
                  </div>

                  <div className="two-column-grid">
                    <article className="card inner-card">
                      <div className="card-top">
                        <span className="pill pill-info">POST /events</span>
                        <span className="muted-copy">create a new event</span>
                      </div>
                      <h3>Create event form</h3>
                      <div className="form-grid">
                        <label className="field">
                          <span>Title</span>
                          <input
                            value={createEventForm.title}
                            onChange={(event) =>
                              setCreateEventForm((current) => ({ ...current, title: event.target.value }))
                            }
                            placeholder="Backend meetup"
                          />
                        </label>
                        <label className="field">
                          <span>Address</span>
                          <input
                            value={createEventForm.address}
                            onChange={(event) =>
                              setCreateEventForm((current) => ({ ...current, address: event.target.value }))
                            }
                            placeholder="Nevsky 1"
                          />
                        </label>
                        <label className="field">
                          <span>Started at</span>
                          <input
                            value={createEventForm.started_at}
                            onChange={(event) =>
                              setCreateEventForm((current) => ({ ...current, started_at: event.target.value }))
                            }
                            placeholder="2026-05-01T18:00:00Z"
                          />
                        </label>
                        <label className="field">
                          <span>Finished at</span>
                          <input
                            value={createEventForm.finished_at}
                            onChange={(event) =>
                              setCreateEventForm((current) => ({ ...current, finished_at: event.target.value }))
                            }
                            placeholder="2026-05-01T20:00:00Z"
                          />
                        </label>
                        <label className="field">
                          <span>Category</span>
                          <select
                            value={createEventForm.category}
                            onChange={(event) =>
                              setCreateEventForm((current) => ({ ...current, category: event.target.value }))
                            }
                          >
                            <option value="">not set</option>
                            {CATEGORY_OPTIONS.map((category) => (
                              <option key={category} value={category}>
                                {category}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="field">
                          <span>Price</span>
                          <input
                            value={createEventForm.price}
                            onChange={(event) =>
                              setCreateEventForm((current) => ({ ...current, price: event.target.value }))
                            }
                            placeholder="1500"
                          />
                        </label>
                        <label className="field">
                          <span>City</span>
                          <input
                            value={createEventForm.city}
                            onChange={(event) =>
                              setCreateEventForm((current) => ({ ...current, city: event.target.value }))
                            }
                            placeholder="Saint Petersburg"
                          />
                        </label>
                        <label className="field wide-field">
                          <span>Description</span>
                          <input
                            value={createEventForm.description}
                            onChange={(event) =>
                              setCreateEventForm((current) => ({ ...current, description: event.target.value }))
                            }
                            placeholder="Internal QA session"
                          />
                        </label>
                      </div>
                      <button type="button" className="primary-button" onClick={createEvent}>
                        Publish event
                      </button>
                    </article>

                    <article className="card inner-card">
                      <div className="card-top">
                        <span className="pill pill-info">PATCH /events/{`{id}`}</span>
                        <span className="muted-copy">edit my existing event</span>
                      </div>
                      <h3>Edit event form</h3>
                      <div className="form-grid">
                        <label className="field">
                          <span>Event ID</span>
                          <input
                            value={editForm.event_id}
                            onChange={(event) =>
                              setEditForm((current) => ({ ...current, event_id: event.target.value }))
                            }
                            placeholder="ObjectId"
                          />
                        </label>
                        <label className="field">
                          <span>Category</span>
                          <select
                            value={editForm.category}
                            onChange={(event) =>
                              setEditForm((current) => ({ ...current, category: event.target.value }))
                            }
                          >
                            <option value="">not set</option>
                            {CATEGORY_OPTIONS.map((category) => (
                              <option key={category} value={category}>
                                {category}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="field">
                          <span>Price</span>
                          <input
                            value={editForm.price}
                            onChange={(event) =>
                              setEditForm((current) => ({ ...current, price: event.target.value }))
                            }
                            placeholder="2000"
                          />
                        </label>
                        <label className="field">
                          <span>City</span>
                          <input
                            value={editForm.city}
                            onChange={(event) =>
                              setEditForm((current) => ({ ...current, city: event.target.value }))
                            }
                            placeholder="Kazan"
                          />
                        </label>
                        <label className="checkbox">
                          <input
                            type="checkbox"
                            checked={editForm.clear_city}
                            onChange={(event) =>
                              setEditForm((current) => ({ ...current, clear_city: event.target.checked }))
                            }
                          />
                          <span>Clear city field</span>
                        </label>
                      </div>
                      <button type="button" className="primary-button" onClick={patchEvent}>
                        Save event changes
                      </button>
                    </article>
                  </div>

                  <div className="cards-grid">
                    {myEvents.length === 0 ? (
                      <div className="empty-state">Load your events and they will appear here.</div>
                    ) : (
                      myEvents.map((event) => (
                        <EventCard
                          key={event.id}
                          event={event}
                          onOpen={openEventCard}
                          onPrepareEdit={prepareEventEditor}
                        />
                      ))
                    )}
                  </div>
                </>
              )}
            </section>
          )}

          {route === "/tech" && (
            <section className="card page-panel">
              <SectionIntro
                eyebrow="Page 5"
                title="Tech Panel"
                description="Оставшиеся service сценарии, ручные lookup по id и raw response inspector."
                actions={
                  <>
                    <button type="button" className="ghost-button" onClick={loadHealth}>
                      Health
                    </button>
                    <button type="button" className="ghost-button" onClick={createAnonymousSession}>
                      New session
                    </button>
                    <button type="button" className="ghost-button" onClick={logoutOrganizer}>
                      Logout
                    </button>
                  </>
                }
              />

              <div className="two-column-grid">
                <article className="card inner-card">
                  <div className="card-top">
                    <span className="pill pill-neutral">GET /users/{`{id}`}</span>
                  </div>
                  <h3>Direct organizer lookup</h3>
                  <label className="field">
                    <span>User ID</span>
                    <input
                      value={techLookup.user_id}
                      onChange={(event) =>
                        setTechLookup((current) => ({ ...current, user_id: event.target.value }))
                      }
                      placeholder="ObjectId"
                    />
                  </label>
                  <button type="button" className="primary-button" onClick={runTechUserLookup}>
                    Open organizer card
                  </button>
                </article>

                <article className="card inner-card">
                  <div className="card-top">
                    <span className="pill pill-neutral">GET /events/{`{id}`}</span>
                  </div>
                  <h3>Direct event lookup</h3>
                  <label className="field">
                    <span>Event ID</span>
                    <input
                      value={techLookup.event_id}
                      onChange={(event) =>
                        setTechLookup((current) => ({ ...current, event_id: event.target.value }))
                      }
                      placeholder="ObjectId"
                    />
                  </label>
                  <button type="button" className="primary-button" onClick={runTechEventLookup}>
                    Open event card
                  </button>
                </article>
              </div>

              <div className="note-box">
                <strong>Included scenarios</strong>
                <p>
                  The site now covers auth, anonymous session bootstrap, event catalog, organizer directory,
                  organizer dashboard, event editing, direct id lookups, and raw response inspection.
                </p>
              </div>
            </section>
          )}
        </section>

        <aside className="sidebar-column">
          <section className="card side-panel">
            <SectionIntro
              eyebrow="Live State"
              title="Current workspace"
              description="The frontend keeps the current organizer and last selected event across pages."
            />

            <div className="workspace-list">
              <div className="workspace-item">
                <span>Health</span>
                <strong>{health?.status ?? "unknown"}</strong>
              </div>
              <div className="workspace-item">
                <span>User ID</span>
                <strong>{currentUser.userId || "not resolved"}</strong>
              </div>
              <div className="workspace-item">
                <span>Username</span>
                <strong>{currentUser.username || "not resolved"}</strong>
              </div>
              <div className="workspace-item">
                <span>Full name</span>
                <strong>{currentUser.fullName || "not resolved"}</strong>
              </div>
              <div className="workspace-item">
                <span>Busy</span>
                <strong>{isBusy ? "request in progress" : "idle"}</strong>
              </div>
            </div>
          </section>

          <section className="card side-panel">
            <SectionIntro
              eyebrow="Focused Event"
              title="Selected event card"
              description="Shared between the catalog, organizer pages and dashboard."
            />

            {selectedEvent ? (
              <EventCard event={selectedEvent} compact />
            ) : (
              <div className="empty-state">Open an event from any page and its card will appear here.</div>
            )}
          </section>

          <section className="card side-panel">
            <SectionIntro
              eyebrow="API Trace"
              title="Last response"
              description="Useful for debugging login, 401 paths and edge cases without leaving the product flow."
            />
            <ResponseInspector response={lastResponse} />
          </section>
        </aside>
      </main>
    </div>
  );
}
