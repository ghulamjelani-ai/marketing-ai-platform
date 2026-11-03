import { useOutletContext } from "react-router-dom";

// Shared dashboard state (Facebook connection, published and scheduled posts) that
// DashboardLayout hands to every page inside it.
export default function useWorkspace() {
  return useOutletContext();
}
