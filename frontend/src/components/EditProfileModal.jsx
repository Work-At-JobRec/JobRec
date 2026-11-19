import { useEffect, useRef, useState } from "react";

const ACCENT = "#E75A8F";

const US_STATES = [
  ["AL", "Alabama"], ["AK", "Alaska"], ["AZ", "Arizona"], ["AR", "Arkansas"],
  ["CA", "California"], ["CO", "Colorado"], ["CT", "Connecticut"], ["DE", "Delaware"],
  ["DC", "District of Columbia"], ["FL", "Florida"], ["GA", "Georgia"], ["HI", "Hawaii"],
  ["ID", "Idaho"], ["IL", "Illinois"], ["IN", "Indiana"], ["IA", "Iowa"],
  ["KS", "Kansas"], ["KY", "Kentucky"], ["LA", "Louisiana"], ["ME", "Maine"],
  ["MD", "Maryland"], ["MA", "Massachusetts"], ["MI", "Michigan"], ["MN", "Minnesota"],
  ["MS", "Mississippi"], ["MO", "Missouri"], ["MT", "Montana"], ["NE", "Nebraska"],
  ["NV", "Nevada"], ["NH", "New Hampshire"], ["NJ", "New Jersey"], ["NM", "New Mexico"],
  ["NY", "New York"], ["NC", "North Carolina"], ["ND", "North Dakota"], ["OH", "Ohio"],
  ["OK", "Oklahoma"], ["OR", "Oregon"], ["PA", "Pennsylvania"], ["RI", "Rhode Island"],
  ["SC", "South Carolina"], ["SD", "South Dakota"], ["TN", "Tennessee"], ["TX", "Texas"],
  ["UT", "Utah"], ["VT", "Vermont"], ["VA", "Virginia"], ["WA", "Washington"],
  ["WV", "West Virginia"], ["WI", "Wisconsin"], ["WY", "Wyoming"],
];

const PROFICIENCY = [
  [1, "1 – Basic"],
  [2, "2 – Intermediate"],
  [3, "3 – Advanced"],
  [4, "4 – Expert"],
];

// "West Lafayette, IN" or "West Lafayette, Indiana" -> { city, state: "IN" }.
// Anything else stays whole in the city box so nothing the parser found is lost.
function splitLocation(location) {
  const text = (location ?? "").trim();
  const comma = text.lastIndexOf(",");
  if (comma !== -1) {
    const tail = text.slice(comma + 1).trim().toLowerCase();
    const match = US_STATES.find(
      ([abbr, name]) => abbr.toLowerCase() === tail || name.toLowerCase() === tail
    );
    if (match) return { city: text.slice(0, comma).trim(), state: match[0] };
  }
  return { city: text, state: "" };
}

function joinLocation(city, state) {
  return [city.trim(), state].filter(Boolean).join(", ");
}

const inputClass =
  "w-full min-w-0 rounded-full border-[1.5px] border-black bg-white px-3 py-1 text-base outline-none focus:border-[#E75A8F]";

function Field({ label, value, onChange, type = "text", placeholder }) {
  return (
    <label className="grid grid-cols-[88px_1fr] items-center gap-2">
      <span className="text-base font-bold">{label}:</span>
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className={inputClass}
      />
    </label>
  );
}

function Box({ children }) {
  return (
    <div className="flex-1 min-w-0 flex flex-col gap-2 rounded-2xl border-[1.5px] border-[#E75A8F] p-3">
      {children}
    </div>
  );
}

function RoundButton({ symbol, label, onClick, disabled }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className="shrink-0 w-8 h-8 inline-flex items-center justify-center rounded-full bg-[#f8d7e6] text-xl font-bold leading-none text-black hover:bg-[#E75A8F] hover:text-white transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
    >
      {symbol}
    </button>
  );
}

function Section({ id, title, children }) {
  return (
    <section id={id} className="scroll-mt-4 mt-7 first:mt-0">
      <h3 className="m-0 mb-3 text-center text-[22px] font-bold">{title}</h3>
      {children}
    </section>
  );
}

function SubLabel({ children }) {
  return <p className="m-0 mt-3 mb-1.5 text-sm font-bold">{children}</p>;
}

/**
 * One editable list (education, work, projects, socials). `fields` describes each
 * entry's inputs; entries are objects, or plain strings when `fields` has one key "".
 */
function ListEditor({ items, onChange, fields, emptyText }) {
  const blank = () => Object.fromEntries(fields.map((f) => [f.key, ""]));
  const [draft, setDraft] = useState(blank);
  const isString = fields.length === 1 && fields[0].key === "";
  const get = (item, key) => (isString ? item : item[key]);
  const set = (item, key, value) => (isString ? value : { ...item, [key]: value });
  const draftFilled = fields.every((f) => draft[f.key].trim());

  const add = () => {
    if (!draftFilled) return;
    onChange([...items, isString ? draft[""].trim() : draft]);
    setDraft(blank());
  };

  return (
    <>
      <SubLabel>Current:</SubLabel>
      {items.length === 0 ? (
        <p className="m-0 text-sm text-[#8a8a8a]">{emptyText}</p>
      ) : (
        <div className="flex flex-col gap-2">
          {items.map((item, i) => (
            <div key={i} className="flex items-center gap-2">
              <Box>
                {fields.map((f) => (
                  <Field
                    key={f.key}
                    label={f.label}
                    value={get(item, f.key)}
                    onChange={(v) => onChange(items.map((it, j) => (j === i ? set(it, f.key, v) : it)))}
                  />
                ))}
              </Box>
              <RoundButton
                symbol="−"
                label={`Remove ${fields.map((f) => get(item, f.key)).join(" ")}`}
                onClick={() => onChange(items.filter((_, j) => j !== i))}
              />
            </div>
          ))}
        </div>
      )}

      <SubLabel>Add:</SubLabel>
      <div className="flex items-center gap-2">
        <Box>
          {fields.map((f) => (
            <Field
              key={f.key}
              label={f.label}
              value={draft[f.key]}
              placeholder={f.placeholder}
              onChange={(v) => setDraft((d) => ({ ...d, [f.key]: v }))}
            />
          ))}
        </Box>
        <RoundButton symbol="+" label="Add" onClick={add} disabled={!draftFilled} />
      </div>
    </>
  );
}

function SkillsEditor({ skills, onChange }) {
  const [name, setName] = useState("");
  const [level, setLevel] = useState("");
  const trimmed = name.trim();
  const duplicate = skills.some((s) => s.skill_name.toLowerCase() === trimmed.toLowerCase());
  const canAdd = trimmed && level && !duplicate;

  const add = () => {
    if (!canAdd) return;
    onChange([...skills, { skill_name: trimmed, proficiency_level: Number(level) }]);
    setName("");
    setLevel("");
  };

  return (
    <>
      {skills.length === 0 ? (
        <p className="m-0 text-sm text-[#8a8a8a]">No skills yet.</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {skills.map((skill) => (
            <span
              key={skill.skill_name}
              className="inline-flex items-center gap-1.5 rounded-full border-2 border-[#E75A8F] py-1 pl-3 pr-2 text-base"
            >
              {skill.skill_name}
              <button
                type="button"
                onClick={() => onChange(skills.filter((s) => s !== skill))}
                aria-label={`Remove ${skill.skill_name}`}
                className="w-5 h-5 inline-flex items-center justify-center rounded-full leading-none text-[#E75A8F] hover:bg-[#E75A8F] hover:text-white transition-colors cursor-pointer"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      <SubLabel>Add skill:</SubLabel>
      <div className="flex items-center gap-2">
        <Box>
          <div className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 items-end">
            <span className="text-base font-bold">Name:</span>
            <span className="text-base font-bold">Proficiency:</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), add())}
              aria-label="Skill name"
              className={inputClass}
            />
            <select
              value={level}
              onChange={(e) => setLevel(e.target.value)}
              aria-label="Proficiency"
              className={`${inputClass} cursor-pointer`}
            >
              <option value="">Select</option>
              {PROFICIENCY.map(([value, text]) => (
                <option key={value} value={value}>{text}</option>
              ))}
            </select>
          </div>
          {duplicate && trimmed && (
            <p className="m-0 text-sm text-red-600">You already have this skill.</p>
          )}
        </Box>
        <RoundButton symbol="+" label="Add skill" onClick={add} disabled={!canAdd} />
      </div>
    </>
  );
}

const EDUCATION_FIELDS = [
  { key: "school", label: "School", placeholder: "Purdue University" },
  { key: "degree", label: "Degree", placeholder: "BS Computer Engineering" },
];
const WORK_FIELDS = [
  { key: "company_name", label: "Company", placeholder: "Apple" },
  { key: "role", label: "Role", placeholder: "Software Engineer" },
];
const PROJECT_FIELDS = [{ key: "", label: "Name", placeholder: "RAG Email Generator" }];
const SOCIAL_FIELDS = [
  { key: "platform", label: "Name", placeholder: "LinkedIn" },
  { key: "url", label: "Link", placeholder: "linkedin.com/in/you" },
];

// The master edit pop-up: every part of the profile in one form, saved together on Update.
export default function EditProfileModal({ profile, initialSection, onSave, onClose }) {
  const location = splitLocation(profile.location);
  const [form, setForm] = useState({
    name: profile.name ?? "",
    email: profile.email ?? "",
    phone: profile.phone ?? "",
    city: location.city,
    state: location.state,
    education: profile.education ?? [],
    employment_history: profile.employment_history ?? [],
    projects: profile.projects ?? [],
    skills: profile.skills ?? [],
    socials: profile.socials ?? [],
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const bodyRef = useRef(null);

  const update = (key) => (value) => setForm((f) => ({ ...f, [key]: value }));

  useEffect(() => {
    const onKeyDown = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  // Opening from a section title (e.g. "Projects") jumps straight to that section
  useEffect(() => {
    if (!initialSection) return;
    bodyRef.current?.querySelector(`#edit-${initialSection}`)?.scrollIntoView({ block: "start" });
  }, [initialSection]);

  const handleSave = async () => {
    setSaving(true);
    setError("");
    try {
      await onSave({
        name: form.name,
        email: form.email,
        phone: form.phone,
        location: joinLocation(form.city, form.state),
        education: form.education,
        employment_history: form.employment_history,
        projects: form.projects,
        skills: form.skills,
        socials: form.socials,
      });
      onClose();
    } catch (err) {
      console.error("Failed to save profile", err);
      setError("Couldn't save your changes. Please try again.");
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Edit profile"
        className="zoom-in relative flex w-full max-w-[520px] max-h-[70vh] flex-col rounded-2xl border-[1.5px] border-black bg-[#fcfcfc]"
      >
        <div className="flex items-center justify-between px-6 pt-5 pb-3">
          <h2 className="m-0 text-2xl font-bold">Edit Profile</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="w-7 h-7 inline-flex items-center justify-center rounded-full text-xl leading-none text-black hover:text-[#ff2d8d] transition-colors cursor-pointer"
          >
            ×
          </button>
        </div>

        <div ref={bodyRef} className="flex-1 overflow-y-auto px-6 pb-4">
          <Section id="edit-profile" title="Contact Info">
            <Box>
              <Field label="Name" value={form.name} onChange={update("name")} />
              <Field label="Email" type="email" value={form.email} onChange={update("email")} />
              <Field label="Phone" type="tel" value={form.phone} onChange={update("phone")} />
              <div className="grid grid-cols-[88px_1fr_auto] items-center gap-2">
                <span className="text-base font-bold">City:</span>
                <input
                  value={form.city}
                  onChange={(e) => update("city")(e.target.value)}
                  aria-label="City"
                  className={inputClass}
                />
                <select
                  value={form.state}
                  onChange={(e) => update("state")(e.target.value)}
                  aria-label="State"
                  className={`${inputClass} w-[84px] cursor-pointer`}
                >
                  <option value="">State</option>
                  {US_STATES.map(([abbr, stateName]) => (
                    <option key={abbr} value={abbr} title={stateName}>{abbr}</option>
                  ))}
                </select>
              </div>
            </Box>
          </Section>

          <Section id="edit-education" title="Education">
            <ListEditor
              items={form.education}
              onChange={update("education")}
              fields={EDUCATION_FIELDS}
              emptyText="No education yet."
            />
          </Section>

          <Section id="edit-work" title="Work Experience">
            <ListEditor
              items={form.employment_history}
              onChange={update("employment_history")}
              fields={WORK_FIELDS}
              emptyText="No work experience yet."
            />
          </Section>

          <Section id="edit-projects" title="Projects">
            <ListEditor
              items={form.projects}
              onChange={update("projects")}
              fields={PROJECT_FIELDS}
              emptyText="No projects yet."
            />
          </Section>

          <Section id="edit-skills" title="Skills">
            <SkillsEditor skills={form.skills} onChange={update("skills")} />
          </Section>

          <Section id="edit-socials" title="Socials">
            <ListEditor
              items={form.socials}
              onChange={update("socials")}
              fields={SOCIAL_FIELDS}
              emptyText="No socials yet."
            />
          </Section>
        </div>

        <div className="flex flex-col items-center gap-2 border-t border-[#e2e2e2] px-6 py-4">
          {error && <p role="alert" className="m-0 text-sm text-red-600">{error}</p>}
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="min-w-[180px] rounded-xl border-none py-2 px-8 text-lg font-bold text-white transition-opacity hover:opacity-90 cursor-pointer disabled:opacity-50 disabled:cursor-wait"
            style={{ backgroundColor: ACCENT }}
          >
            {saving ? "Saving…" : "Update"}
          </button>
        </div>
      </div>
    </div>
  );
}
