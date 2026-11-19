import { useCallback, useEffect, useRef, useState } from "react";
import Navbar from "../components/Navbar.jsx";
import Avatar from "../components/Avatar.jsx";
import MenuItem from "../components/MenuItem.jsx";
import { EditIcon } from "../components/Icons.jsx";
import EditProfileModal from "../components/EditProfileModal.jsx";
import { useAuthenticatedUser } from "../hooks/useAuthenticatedUser.ts";
import { useNavigate } from "react-router-dom";

const PLACEHOLDER_CONTACT = {
  name: null,
  email: null,
  phone: null,
  location: null,
};

const EMPTY_PROFILE = {
  name: null,
  email: null,
  phone: null,
  location: null,
  skills: [],
  education: [],
  projects: [],
  socials: [],
  employment_history: [],
};

// The backend doesn't report parsing progress, so estimate it: ease toward 95% and
// hold there until the profile poll reports the parse is done
function ResumeProgress() {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setProgress((p) => p + (95 - p) * 0.02);
    }, 200);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="relative mx-auto my-[30px] w-[110px] h-[110px]">
      <div className="spinner w-full h-full rounded-full"></div>
      <div className="absolute inset-0 flex items-center justify-center text-black text-xl font-bold">
        {Math.floor(progress)}%
      </div>
    </div>
  );
}

function LeftPanel({
  processing,
  userInfo,
  onUpload,
  selectedFile,
  onFileChange,
  uploadError,
  onEditProfile,
}) {
  const contact = userInfo ?? PLACEHOLDER_CONTACT;

  return (
    <section className="border-r border-[#bdbdbd] text-center p-[34px_34px_40px] md:border-r md:border-b-0 border-b">
      {/* Center within one viewport height (minus navbar and padding) rather than the whole
          section, so the panel doesn't drift down when the right panel grows after parsing */}
      <div className="flex flex-col justify-center md:min-h-[calc(100vh-58px-74px)]">
      <h1 className="m-0 mb-6 text-[30px] font-bold">
        {processing ? (
          "Your Profile:"
        ) : (
          <button
            type="button"
            onClick={() => onEditProfile("profile")}
            title="Edit profile"
            className="inline-flex items-center gap-3 text-black hover:text-[#E75A8F] transition-colors cursor-pointer"
          >
            <EditIcon className="w-8 h-8" />
            Your Profile:
          </button>
        )}
      </h1>
      {contact.name && <p className="m-0 text-2xl font-bold">{contact.name}</p>}
      {contact.email && <p className="m-0 mt-1 text-2xl font-bold">{contact.email}</p>}
      {contact.phone && <p className="m-0 mt-1 text-2xl font-bold">{contact.phone}</p>}
      {contact.location && (
        <div className="mt-2.5 text-[#9b9b9b] text-[17px] inline-flex items-center justify-center gap-1.5">
          <span>📍</span>
          <span>{contact.location}</span>
        </div>
      )}

      {/* Show placeholder message while parsing */}
      {!contact.name && processing && (
        <p className="text-[#8a8a8a] mt-2">
          Profile information will appear after parsing.
        </p>
      )}

      <Avatar editable={!processing} />

      {processing ? (
        <>
          <div className="text-black text-2xl mt-2 mb-[18px]">Parsing resume...</div>
          <ResumeProgress />
        </>
      ) : (
        <>
          <div className="text-xl font-bold my-2 mb-[18px]">Autofill Profile with Resume:</div>
          
      <form
        onSubmit={onUpload}
        className="flex flex-col items-center gap-4"
      >
        <label
          htmlFor="resume"
          className="inline-flex items-center justify-center min-w-[260px] border-none rounded-2xl bg-black text-white text-[19px] font-bold py-4 px-6 cursor-pointer hover:bg-gray-800 transition-colors"
        >
          {selectedFile ? "Change resume" : "Choose resume"}
        </label>

        <input
          type="file"
          id="resume"
          name="resume"
          accept=".pdf,.docx"
          className="sr-only"
          onChange={(e) => {
            onFileChange(e.target.files?.[0] ?? null);
          }}
        />

        {selectedFile ? (
          <div role="status" className="text-center">
            <p className="text-green-700 font-semibold">
              ✓ File selected
            </p>

            <p className="text-[16px] text-black break-all">
              {selectedFile.name}
            </p>

            <p className="text-[14px] text-gray-500 mt-1">
              Ready to upload. Click Upload &amp; Parse to begin.
            </p>
          </div>
        ) : (
          <p className="text-[14px] text-gray-500">
            No file selected. Accepts PDF or DOCX.
          </p>
        )}

        {uploadError && (
          <p role="alert" className="text-red-600 text-sm">
            {uploadError}
          </p>
        )}

        <button
          type="submit"
          disabled={!selectedFile}
          className="rounded-xl border border-[#ff2d8d] bg-transparent px-8 py-2 text-[17px] font-semibold text-[#ff2d8d] transition-colors hover:bg-[#ff2d8d] hover:text-white cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Upload &amp; Parse
        </button>
      </form>
        </>
      )}
      </div>
    </section>
  );
}

const SKILL_PREVIEW_COUNT = 5;

// Read-only chips; skills are added and removed in the edit pop-up
function SkillChips({ skills }) {
  return (
    <div className="flex flex-wrap gap-2">
      {skills.map((skill) => (
        <span
          key={skill.skill_name}
          className="inline-flex items-center border-2 border-[#E75A8F] rounded-full py-1 px-3 text-base"
        >
          {skill.skill_name}
        </span>
      ))}
    </div>
  );
}

// Show a short preview of skills; the full list opens in a pop-up so it doesn't flood the profile
function SkillsList({ skills }) {
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    if (!showAll) return;
    const onKeyDown = (e) => e.key === "Escape" && setShowAll(false);
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [showAll]);

  return (
    <>
      <SkillChips skills={skills.slice(0, SKILL_PREVIEW_COUNT)} />
      {skills.length > SKILL_PREVIEW_COUNT && (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="mt-3 bg-transparent text-base font-semibold text-black hover:text-[#ff2d8d] transition-colors cursor-pointer"
        >
          See more ({skills.length - SKILL_PREVIEW_COUNT})
        </button>
      )}

      {showAll && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 px-4"
          onClick={() => setShowAll(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="All skills"
            className="zoom-in relative w-full max-w-[520px] max-h-[70vh] overflow-y-auto rounded-2xl border-[1.5px] border-black bg-[#fcfcfc] p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="m-0 text-xl font-bold">All skills</h3>
              <button
                type="button"
                onClick={() => setShowAll(false)}
                aria-label="Close"
                className="w-7 h-7 inline-flex items-center justify-center rounded-full text-xl text-black hover:text-[#ff2d8d] transition-colors leading-none cursor-pointer"
              >
                ×
              </button>
            </div>
            <SkillChips skills={skills} />
          </div>
        </div>
      )}
    </>
  );
}

// A section heading that opens the edit pop-up at that section; icon and text turn pink on hover
function SectionTitle({ label, section, onEdit }) {
  return (
    <h3 className="m-0 my-[30px] text-2xl font-bold">
      <button
        type="button"
        onClick={() => onEdit(section)}
        title={`Edit ${label.replace(":", "").toLowerCase()}`}
        className="inline-flex items-center gap-4 text-black hover:text-[#E75A8F] transition-colors cursor-pointer"
      >
        <EditIcon className="w-[22px] h-[22px] shrink-0" />
        {label}
      </button>
    </h3>
  );
}

function RightPanel({ userInfo, onEdit }) {
  if (userInfo) {
    return (
      <section className="relative flex flex-col justify-center p-[34px_34px_40px]">
        <h2 className="m-0 mb-7 text-center text-[26px] font-bold">Your current information:</h2>
        <div className="mx-auto max-w-[320px] w-full">
          <SectionTitle label="Education:" section="education" onEdit={onEdit} />
          <ul>
            {userInfo.education.map((edu, i) => (
              <li key={i}>
                {edu.degree} from {edu.school}
              </li>
            ))}
          </ul>

          <SectionTitle label="Work Experience:" section="work" onEdit={onEdit} />
          <ul>
            {userInfo.employment_history.map((work, i) => (
              <li key={i}>
                {work.role} at {work.company_name}
              </li>
            ))}
          </ul>

          <SectionTitle label="Projects:" section="projects" onEdit={onEdit} />
          <ul>
            {userInfo.projects.map((project, i) => (
              <li key={i}>{project}</li>
            ))}
          </ul>

          <SectionTitle label="Skills:" section="skills" onEdit={onEdit} />
          {/* Proficiency levels stay in the database for recommendations but aren't shown */}
          <SkillsList skills={userInfo.skills} />

          <SectionTitle label="Socials:" section="socials" onEdit={onEdit} />
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
        <SectionTitle label="Education:" section="education" onEdit={onEdit} />
        <SectionTitle label="Work Experience:" section="work" onEdit={onEdit} />
        <SectionTitle label="Projects:" section="projects" onEdit={onEdit} />
        <SectionTitle label="Skills:" section="skills" onEdit={onEdit} />
        <SectionTitle label="Socials:" section="socials" onEdit={onEdit} />
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
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadError, setUploadError] = useState("");
  const [userPersonal, setUserpersonal] = useState(null);
  // Which section the edit pop-up opened at, or null when it's closed
  const [editSection, setEditSection] = useState(null);
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

    if (!selectedFile) return;

    const previousStatus = status;
    setUploadError("");

    try {
      const token = await getAccessTokenSilently();

      const formData = new FormData();
      formData.append("resume", selectedFile);

      setStatus("processing");

      const response = await fetch("/upload", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
        redirect: "error",
      });

      if (!response.ok) {
        throw new Error(`Upload failed: ${response.status}`);
      }

      setSelectedFile(null);
      await fetchProfile();

    } catch (error) {
      console.error("Resume upload failed:", error);

      setStatus(previousStatus);
      setUploadError(
        "Failed to upload resume. Please check your file and try again."
      );
    }
  };


  // Saves the whole edited profile; throws so the edit pop-up can show the error and stay open
  const handleSaveProfile = async (profile) => {
    const token = await getAccessTokenSilently();
    const res = await fetch("/api/update_profile", {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(profile),
    });
    if (!res.ok) throw new Error(`Status ${res.status}`);
    const data = await res.json();
    setUserInfo(data.user_info);
  };

  const processing = status === "processing";

  return (
    <div className="min-h-screen">
      <div className="w-full min-h-screen bg-[#f4f4f4]">
        <Navbar />
        <main className="grid md:grid-cols-[42%_58%] grid-cols-1 min-h-[calc(100vh-58px)] items-stretch">
          <LeftPanel
            processing={processing}
            userInfo={userInfo}
            onUpload={handleUpload}
            selectedFile={selectedFile}
            onFileChange={(file) => {
              setSelectedFile(file);
              setUploadError("");
            }}
            uploadError={uploadError}
            onEditProfile={setEditSection}
          />
          {processing ? <ProcessingRightPanel /> : <RightPanel userInfo={userInfo} onEdit={setEditSection} />}
        </main>
        {editSection && !processing && (
          <EditProfileModal
            profile={userInfo ?? EMPTY_PROFILE}
            initialSection={editSection}
            onSave={handleSaveProfile}
            onClose={() => setEditSection(null)}
          />
        )}
      </div>
    </div>
  );
}
