import { Link } from "react-router-dom";
import { useAuth0 } from "@auth0/auth0-react";

export default function Navbar() {
  const { loginWithRedirect } = useAuth0();
  const { isAuthenticated, isLoading } = useAuth0();

  return (
    <header className="bg-black text-white grid grid-cols-[1.5fr_1fr_1fr_1fr] items-center py-2.5 px-[18px] min-h-[58px] w-full">
      <Link
        to="/"
        className="text-[30px] font-bold justify-self-start no-underline text-white hover:text-[#E75A8F] transition-colors"
      >
        JobRec
      </Link>
      <span className="text-[28px] font-bold justify-self-center opacity-50 cursor-default hover:text-[#E75A8F] transition-colors">
        Jobs
      </span>
      <span className="text-[28px] font-bold justify-self-center opacity-50 cursor-default hover:text-[#E75A8F] transition-colors">
        Search
      </span>
      {isAuthenticated ? <Link
        to="/profile"
        className="text-[28px] font-bold justify-self-center text-white hover:text-[#E75A8F] transition-colors"
      >
        Profile
      </Link> : 
      <button
        onClick = {() => loginWithRedirect()} 
        className="text-[28px] font-bold justify-self-center text-white hover:text-[#E75A8F] transition-colors"
      >
        Log In
      </button>
      }
    </header>
  );
}
