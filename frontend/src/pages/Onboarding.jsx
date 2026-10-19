import Navbar from "../components/Navbar.jsx";
import { useAuthenticatedUser } from "../hooks/useAuthenticatedUser.ts";
import { useEffect, useState } from "react";
export default function Onboarding() {
      const { isAuthenticated, isLoading,  accessToken} = useAuthenticatedUser();
      const [formData, setFormData] = useState(null);
      function handleSubmit(e){
        // Prevent the browser from reloading the page
        e.preventDefault();
        // Read the form data
        const form = e.target;
        const data = new FormData(form);
        setFormData(data);
      }

      useEffect(() => {async function send_data() {
         if(formData && accessToken){
            try { 
            const res = await fetch("/api/onboarding", {headers: {
                Authorization: `Bearer ${accessToken}`
                }, body: formData,
                   method: 'POST'});
            if(res.status != 200){
                console.error(`attempt to submit onboarding results got response ${res.status}`)
            } else {
                window.location.href = "/profile";
            }
        } catch (err) {
            console.error("Failed to submit onboarding results", err);
            }
        }
        
      }
      send_data();
       
      }, [accessToken, formData]);
      
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
            <button
              type="submit"
              className="rounded-xl border border-[#ff2d8d] bg-transparent px-8 py-2 text-[17px] font-semibold text-[#ff2d8d] transition-colors hover:bg-[#ff2d8d] hover:text-white cursor-pointer"
            >
              Submit
            </button>
          </form>
        </div>
      );
    }
