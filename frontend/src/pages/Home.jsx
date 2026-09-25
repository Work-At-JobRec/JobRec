import Navbar from "../components/Navbar.jsx";
import { useAuth0 } from "@auth0/auth0-react";

export default function Home() {
  const { isAuthenticated, isLoading, user, loginWithRedirect, logout } = useAuth0();
  return (
    <div className="flex flex-col items-center min-h-screen text-center">
      <Navbar />
      <div className="text-[96px] font-bold text-black mt-20 mb-5">JobRec</div>
      <div className="text-[22px] max-w-[800px] text-black mb-[30px] leading-relaxed">
        The applicant-focused job board you didn't know you needed!
      </div>
      <div className="text-[15px] text-black">
        Sharvari Deshpande, Luna Brown, Luke McCartney, and Pranav Putta
      </div>
      <div>
        {isLoading ? 
          <div>loading...</div>          
        : isAuthenticated ?<div >welcome, {user.name}</div>: <div>not logged in...
        </div>
        }
      </div>
    </div>
  );
}
