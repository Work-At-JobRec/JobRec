import { useCallback, useEffect, useRef, useState } from "react";
import Navbar from "../components/Navbar.jsx";
import Avatar from "../components/Avatar.jsx";
import MenuItem from "../components/MenuItem.jsx";
import { useAuthenticatedUser } from "../hooks/useAuthenticatedUser.ts";
import { useNavigate } from "react-router-dom";

const PLACEHOLDER_CONTACT = {
  name: "Jane Smith",
  email: "janesmith100@gmail.com",
  phone: "(+1) 650-890-0093",
  address: "West Lafayette, IN",
};

function LeftPanel({ processing, userInfo, onUpload }) {
  const contact = userInfo ?? PLACEHOLDER_CONTACT;

  return (
    <section className="border-r border-[#bdbdbd] text-center p-[34px_34px_40px] md:border-r md:border-b-0 border-b">
      {/* Center within one viewport height (minus navbar and padding) rather than the whole
          section, so the panel doesn't drift down when the right panel grows after parsing */}
      <div className="flex flex-col justify-center md:min-h-[calc(100vh-58px-74px)]">
      <h1 className="m-0 mb-6 text-[30px] font-bold">Your Profile</h1>
      {contact.name && <p className="m-0 text-2xl font-bold">{contact.name}</p>}
      {contact.email && <p className="m-0 mt-1 text-2xl font-bold">{contact.email}</p>}
      {contact.phone && <p className="m-0 mt-1 text-2xl font-bold">{contact.phone}</p>}
      {contact.address && (
        <div className="mt-2.5 text-[#9b9b9b] text-[17px] inline-flex items-center justify-center gap-1.5">
          <span>📍</span>
          <span>{contact.address}</span>
        </div>
      )}

      <Avatar editable={!processing} />

      {processing ? (
        <>
          <div className="text-black text-2xl mt-2 mb-[18px]">Parsing resume...</div>
          <div className="spinner mx-auto my-[30px] w-[110px] h-[110px] rounded-full"></div>
        </>
      ) : (
        <>
          <div className="text-xl font-bold my-2 mb-[18px]">Autofill Profile with Resume:</div>
          <form onSubmit={onUpload}>
            <label
              htmlFor="resume"
              className="inline-flex items-center justify-center min-w-[260px] border-none rounded-2xl bg-black text-white text-[19px] font-bold py-4 px-6 cursor-pointer"
            >
              Upload resume
            </label>
            <br />
            <br />
            <input type="file" id="resume" name="resume" accept=".pdf,.doc,.docx" className="hidden" />
            <input type="submit" value="Submit" />
            <br />
            <br />
          </form>
        </>
      )}
      </div>
    </section>
  );
}

function RightPanel({ userInfo, onRemoveSkill }) {
  if (userInfo) {
    return (
      <section className="relative flex flex-col justify-center p-[34px_34px_40px]">
        <h2 className="m-0 mb-7 text-center text-[26px] font-bold">Your current information:</h2>
        <div className="mx-auto max-w-[320px] w-full">
          <MenuItem label="Education:" />
          <ul>
            {userInfo.education.map((edu, i) => (
              <li key={i}>
                {edu.degree} from {edu.school}
              </li>
            ))}
          </ul>

          <MenuItem label="Work Experience:" />
          <ul>
            {userInfo.employment_history.map((work, i) => (
              <li key={i}>
                {work.role} at {work.company_name}
              </li>
            ))}
          </ul>

          <MenuItem label="Projects:" />
          <ul>
            {userInfo.projects.map((project, i) => (
              <li key={i}>{project}</li>
            ))}
          </ul>

          <MenuItem label="Skills:" />
          {/* Proficiency levels stay in the database for recommendations but aren't shown */}
          <div className="flex flex-wrap gap-2">
            {userInfo.skills.map((skill) => (
              <span
                key={skill.skill_name}
                className="inline-flex items-center gap-1.5 border-2 border-[#E75A8F] rounded-full py-1 pl-3 pr-2 text-base"
              >
                {skill.skill_name}
                <button
                  type="button"
                  onClick={() => onRemoveSkill(skill.skill_name)}
                  aria-label={`Remove ${skill.skill_name}`}
                  className="w-5 h-5 inline-flex items-center justify-center rounded-full text-[#E75A8F] hover:bg-[#E75A8F] hover:text-white transition-colors leading-none"
                >
                  ×
                </button>
              </span>
            ))}
          </div>

          <MenuItem label="Socials:" />
          <ul>
            {userInfo.socials.map((social, i) => (
              <li key={i}>
                <a href={social.url} target="_blank" rel="noreferrer">
                  {social.platform}
                </a>
              </li>
            ))}
          </ul>
        </div>
      </section>
    );
  }

  return (
    <section className="relative flex flex-col justify-center p-[34px_34px_40px]">
      <h2 className="m-0 mb-7 text-center text-[26px] font-bold">Or, Manually Add Information:</h2>
      <div className="mx-auto max-w-[320px] w-full">
        <MenuItem label="Education:" />
        <MenuItem label="Work Experience:" />
        <MenuItem label="Projects:" />
        <MenuItem label="Skills:" />
        <MenuItem label="Socials:" />
      </div>
    </section>
  );
}

function ProcessingRightPanel() {
  return (
    <section className="relative flex flex-col justify-center p-[34px_34px_40px]">
      <h2 className="m-0 mb-7 text-center text-[26px] font-bold">Your information will appear here:</h2>
      <div className="mx-auto max-w-[320px] w-full">
        <MenuItem label="Education:" />
        <MenuItem label="Work Experience:" />
        <MenuItem label="Projects:" />
        <MenuItem label="Skills:" />
        <MenuItem label="Socials:" />
      </div>
    </section>
  );
}

export default function Profile() {
  const navigate = useNavigate();
  const [status, setStatus] = useState("loading");
  const [userInfo, setUserInfo] = useState(null);
  const [userPersonal, setUserpersonal] = useState(null);
  const pollTimer = useRef(null);
  const {
    isAuthenticated,
    isLoading,
    getAccessTokenSilently,
    error: authError,
  } = useAuthenticatedUser();

  const fetchProfile = useCallback(async () => {
  try {
    const token = await getAccessTokenSilently();

    const res = await fetch("/api/profile", {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!res.ok) {
      throw new Error(`Profile request failed: ${res.status}`);
    }

    const data = await res.json();
    setStatus(data.status);
    setUserInfo(data.user_info ?? null);

  } catch (err) {
    console.error("Failed to fetch profile:", err);
    setStatus("error");
  }
}, [getAccessTokenSilently]);

  useEffect(() => {
  if (status === "empty") {
    navigate("/onboarding", { replace: true });
  }
}, [status, navigate]);

  useEffect(() => {
  if (isAuthenticated && !isLoading) {
    fetchProfile();
  }
}, [isAuthenticated, isLoading, fetchProfile]);

  useEffect(() => {
    if (status !== "processing") return;
    pollTimer.current = setInterval(fetchProfile, 2000);
    return () => clearInterval(pollTimer.current);
  }, [status, fetchProfile]);

  const handleUpload = async (e) => {
    e.preventDefault();
    const fileInput = e.target.elements.resume;
    const token = await getAccessTokenSilently();
    if (!fileInput.files.length) return;

    const formData = new FormData();
    formData.append("resume", fileInput.files[0]);

    setStatus("processing");
    await fetch("/upload", { method: "POST", body: formData, headers: {
          Authorization: `Bearer ${token}`
        }});
    fetchProfile();
  };

  const handleRemoveSkill = async (skillName) => {
    // Remove immediately so the chip disappears on click; resync if the server rejects it
    setUserInfo((prev) => ({
      ...prev,
      skills: prev.skills.filter((s) => s.skill_name !== skillName),
    }));
    try {
      const token = await getAccessTokenSilently();
      const res = await fetch("/api/profile/skills", {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ skill_name: skillName }),
      });
      if (!res.ok) throw new Error(`Status ${res.status}`);
    } catch (err) {
      console.error("Failed to remove skill", err);
      fetchProfile();
    }
  };

  const processing = status === "processing";

  return (
    <div className="min-h-screen">
      <div className="w-full min-h-screen bg-[#f4f4f4]">
        <Navbar />
        <main className="grid md:grid-cols-[42%_58%] grid-cols-1 min-h-[calc(100vh-58px)] items-stretch">
          <LeftPanel processing={processing} userInfo={userInfo} onUpload={handleUpload} />
          {processing ? <ProcessingRightPanel /> : <RightPanel userInfo={userInfo} onRemoveSkill={handleRemoveSkill} />}
        </main>
      </div>
    </div>
  );
}
