import { useCallback, useEffect, useRef, useState } from "react";
import Navbar from "../components/Navbar.jsx";
import Avatar from "../components/Avatar.jsx";
import MenuItem from "../components/MenuItem.jsx";

function LeftPanel({ processing, onUpload }) {
  return (
    <section className="border-r border-[#bdbdbd] text-center flex flex-col justify-center p-[34px_34px_40px] md:border-r md:border-b-0 border-b">
      <h1 className="m-0 mb-6 text-[30px] font-bold">Your Profile</h1>
      <p className="m-0 text-2xl font-bold">Jane Smith</p>
      <p className="m-0 mt-1 text-2xl font-bold">janesmith100@gmail.com</p>
      <p className="m-0 mt-1 text-2xl font-bold">(+1) 650-890-0093</p>
      <div className="mt-2.5 text-[#9b9b9b] text-[17px] inline-flex items-center justify-center gap-1.5">
        <span>📍</span>
        <span>West Lafayette, IN</span>
      </div>

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
    </section>
  );
}

function RightPanel({ userInfo }) {
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
          <ul>
            {userInfo.skills.map((skill, i) => (
              <li key={i}>
                {skill.skill_name}: {skill.proficiency_level}/4
              </li>
            ))}
          </ul>

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
  const [status, setStatus] = useState("loading");
  const [userInfo, setUserInfo] = useState(null);
  const pollTimer = useRef(null);

  const fetchProfile = useCallback(async () => {
    try {
      const res = await fetch("/api/profile");
      const data = await res.json();
      setStatus(data.status);
      setUserInfo(data.user_info ?? null);
    } catch (err) {
      console.error("Failed to fetch profile status", err);
    }
  }, []);

  useEffect(() => {
    fetchProfile();
  }, [fetchProfile]);

  useEffect(() => {
    if (status !== "processing") return;
    pollTimer.current = setInterval(fetchProfile, 2000);
    return () => clearInterval(pollTimer.current);
  }, [status, fetchProfile]);

  const handleUpload = async (e) => {
    e.preventDefault();
    const fileInput = e.target.elements.resume;
    if (!fileInput.files.length) return;

    const formData = new FormData();
    formData.append("resume", fileInput.files[0]);

    setStatus("processing");
    await fetch("/upload", { method: "POST", body: formData });
    fetchProfile();
  };

  const processing = status === "processing";

  return (
    <div className="min-h-screen">
      <div className="w-full min-h-screen bg-[#f4f4f4]">
        <Navbar />
        <main className="grid md:grid-cols-[42%_58%] grid-cols-1 min-h-[calc(100vh-58px)] items-stretch">
          <LeftPanel processing={processing} onUpload={handleUpload} />
          {processing ? <ProcessingRightPanel /> : <RightPanel userInfo={userInfo} />}
        </main>
      </div>
    </div>
  );
}
