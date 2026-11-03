import ActivityPanel from "../components/ActivityPanel";
import NotificationsPanel from "../components/NotificationsPanel";
import PostInsights from "../components/PostInsights";
import useWorkspace from "../hooks/useWorkspace";

export default function History() {
  const { activity } = useWorkspace();

  return (
    <>
      <PostInsights />
      <NotificationsPanel />
      <ActivityPanel posts={activity.posts} total={activity.total} />
    </>
  );
}
