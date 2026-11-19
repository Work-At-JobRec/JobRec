import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthenticatedUser } from "../hooks/useAuthenticatedUser";
import Navbar from "../components/Navbar";

const fields = [
  { name: "name", label: "Name", type: "text" },
  { name: "email", label: "Email", type: "email" },
  { name: "phone", label: "Phone Number", type: "tel" },
  { name: "address", label: "Address", type: "text" },
];

export default function Onboarding() {
      const { isAuthenticated, isLoading,  getAccessTokenSilently} = useAuthenticatedUser();
      const [formData, setFormData] = useState(null);
      const navigate = useNavigate();
      const [isSkipping, setIsSkipping] = useState(false);
      const [skipError, setSkipError] = useState("");

      async function handleSkip() {
        if (isLoading || !isAuthenticated || isSkipping) return;

        setIsSkipping(true);
        setSkipError("");

        try {
          const accessToken = await getAccessTokenSilently();

          const response = await fetch("/api/onboarding/skip", {
            method: "POST",
            headers: {
              Authorization: `Bearer ${accessToken}`,
            },
          });

          if (!response.ok) {
            throw new Error(`Skip failed: ${response.status}`);
          }

          navigate("/profile", { replace: true });
        } catch (error) {
          console.error("Failed to skip onboarding:", error);
          setSkipError("Could not skip onboarding. Please try again.");
          setIsSkipping(false);
        }
      }
      function handleSubmit(e){
        // Prevent the browser from reloading the page
        e.preventDefault();
        // Read the form data
        const form = e.target;
        const data = new FormData(form);
        setFormData(data);
      }

      useEffect(() => {async function send_data() {
         if(formData && isAuthenticated && !isLoading){
            try { 
              const accessToken = await getAccessTokenSilently();
            const res = await fetch("/api/onboarding", {headers: {
                Authorization: `Bearer ${accessToken}`
                }, body: formData,
                   method: 'POST'});
            if(res.status != 200){
                console.error(`attempt to submit onboarding results got response ${res.status}`)
            } else {
                navigate("/profile");
            }
        } catch (err) {
            console.error("Failed to submit onboarding results", err);
            }
        }
        
      }
      send_data();
       
      }, [isAuthenticated, isLoading, formData]);
      
      const label = "block mb-2 text-left text-[17px] font-bold text-black";
      const input = "w-full border-[1.5px] border-black rounded-full px-4 py-2 bg-transparent text-black outline-none focus:border-[#ff2d8d]";

      return (
        <div className="flex flex-col items-center min-h-screen text-center">
          <Navbar />
          <div className="text-[96px] font-bold text-black mt-20 mb-5">Welcome, new user</div>
          <div className="text-[22px] text-black text-center mb-[30px]">Complete your profile:</div>

          <form onSubmit={handleSubmit} className="w-full max-w-[640px] px-4">
            <div className="grid gap-6 mb-8 md:grid-cols-2">
                <div>
                    <label htmlFor="name" className={label}>Name</label>
                    <input type="text" id="name" name="name" className={input} required />
                </div>
                <div>
                    <label htmlFor="email" className={label}>Email</label>
                    <input type="email" id="email" name="email" className={input} required />
                </div>
                <div>
                    <label htmlFor="phone" className={label}>Phone Number</label>
                    <input type="tel" id="phone" name="phone" className={input} required />
                </div>
                <div>
                    <label htmlFor="address" className={label}>Address</label>
                    <input type="text" id="address" name="address" className={input} required />
                </div>
            </div>
            <div className="flex justify-center gap-4">
            <button
              type="submit"
              className="rounded-xl border border-[#ff2d8d] bg-transparent px-8 py-2 text-[17px] font-semibold text-[#ff2d8d] transition-colors hover:bg-[#ff2d8d] hover:text-white cursor-pointer"
            >
              Submit
            </button>

            <button
              type="button"
              onClick={handleSkip}
              disabled={isSkipping || isLoading || !isAuthenticated}
              className="rounded-xl border border-gray-400 bg-transparent px-8 py-2 text-[17px] font-semibold text-gray-600 transition-colors hover:bg-gray-200 cursor-pointer disabled:opacity-50"
            >
              {isSkipping ? "Skipping..." : "Skip"}
            </button>
          </div>

          {skipError && (
            <p role="alert" className="mt-4 text-red-600">
              {skipError}
            </p>
          )}
          </form>
        </div>
      );
    }
