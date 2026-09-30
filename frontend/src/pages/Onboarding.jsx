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
      
      return (
        <div className="flex flex-col items-center min-h-screen pt-20 text-center">
          <div className="text-[96px] font-bold text-black mt-20 mb-5">Welcome, new user</div>
          <div className="text-[22px] text-black text-center">Complete your profile:</div>
          
          <form onSubmit={handleSubmit}>
            <div className="grid gap-6 mb-6 md:grid-cols-2">
                <div>
                    <label for="name" className="block mb-2.5 text-sm font-medium text-heading">Name</label>
                    <input type="text" id="name" name="name" className="bg-neutral-secondary-medium border border-default-medium text-heading text-sm rounded-base focus:ring-brand focus:border-brand block w-full px-3 py-2.5 shadow-xs text-body" required />
                </div>
                <div>
                    <label for="email" className="block mb-2.5 text-sm font-medium text-heading">Email</label>
                    <input type="email" id="email" name="email" className="bg-neutral-secondary-medium border border-default-medium text-heading text-sm rounded-base focus:ring-brand focus:border-brand block w-full px-3 py-2.5 shadow-xs text-body" required />
                </div>
                <div>
                    <label for="phone" className="block mb-2.5 text-sm font-medium text-heading">Phone Number</label>
                    <input type="tel" id="phone" name="phone" className="bg-neutral-secondary-medium border border-default-medium text-heading text-sm rounded-base focus:ring-brand focus:border-brand block w-full px-3 py-2.5 shadow-xs text-body" required />
                </div>
                <div>
                    <label for="address" className="block mb-2.5 text-sm font-medium text-heading">Address</label>
                    <input type="text" id="address" name="address" className="bg-neutral-secondary-medium border border-default-medium text-heading text-sm rounded-base focus:ring-brand focus:border-brand block w-full px-3 py-2.5 shadow-xs text-body" required />
                </div>
            </div>
            <button type="submit" class="text-black bg-brand box-border border">Submit</button>
          </form>
        </div>
      );
    }