import {
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { getCameras } from "@/api/cameras";
import { useAuth } from "@/store/useAuth";

import { createSocket } from "./socket";
import {
  SocketContext,
  type SocketConnectionState,
} from "./SocketContext";
import {
  SOCKET_EVENTS,
  type SocketAlert,
} from "./events";

import { useQuery, useQueryClient } from "@tanstack/react-query";


import {
  getLastSeenTimestamp,
  setLastSeenTimestamp,
} from "./lastSeen";

interface SocketProviderProps {
  children: ReactNode;
}

export default function SocketProvider({
  children,
}: SocketProviderProps) {
  const { accessToken, isAuthenticated } = useAuth();

  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] =
    useState<string | null>(null);

  const queryClient = useQueryClient();
  const camerasQuery = useQuery({
    queryKey: ["cameras"],
    queryFn: getCameras,
    enabled: isAuthenticated,
  });

  const cameraIds = useMemo(
    () => camerasQuery.data?.map((camera) => camera.id) ?? [],
    [camerasQuery.data],
  );

  const socket = useMemo(() => {
    if (!isAuthenticated || !accessToken) {
      return null;
    }

    return createSocket(accessToken);
  }, [accessToken, isAuthenticated]);

  useEffect(() => {
    if (!socket || !camerasQuery.data) {
      return;
    }

    const handleConnect = () => {
      console.log("[Socket] connected:", socket.id);

      setIsConnected(true);
      setConnectionError(null);

      const lastSeenTimestamp = getLastSeenTimestamp();

      console.log("[Socket] joining cameras:", cameraIds);
      console.log("[Socket] last seen:", lastSeenTimestamp);

      socket.emit("join", {
        camera_ids: cameraIds,
        ...(lastSeenTimestamp
          ? { last_seen_timestamp: lastSeenTimestamp }
          : {}),
      });
    };

    const handleDisconnect = (reason: string) => {
      console.log("[Socket] disconnected:", reason);
      setIsConnected(false);
    };

    const handleConnectError = (error: Error) => {
      console.error("[Socket] connection error:", error.message);

      setIsConnected(false);
      setConnectionError(error.message);
    };

    const handleNewAlert = (alert: SocketAlert) => {
      console.log("[Socket] alert:new", alert);

      if (alert.created_at) {
        setLastSeenTimestamp(alert.created_at);
      }

      queryClient.invalidateQueries({
        queryKey: ["alerts"],
      });
    };

    const handleUpdatedAlert = (alert: SocketAlert) => {
      console.log("[Socket] alert:updated", alert);

      queryClient.invalidateQueries({
        queryKey: ["alerts"],
      });
    };

    const handleMissedAlert = (alert: SocketAlert) => {
      console.log("[Socket] alert:missed", alert);

      if (alert.created_at) {
        setLastSeenTimestamp(alert.created_at);
      }

      queryClient.invalidateQueries({
        queryKey: ["alerts"],
      });
    };

    socket.on("connect", handleConnect);
    socket.on("disconnect", handleDisconnect);
    socket.on("connect_error", handleConnectError);

    socket.on(SOCKET_EVENTS.ALERT_NEW, handleNewAlert);
    socket.on(SOCKET_EVENTS.ALERT_UPDATED, handleUpdatedAlert);
    socket.on(SOCKET_EVENTS.ALERT_MISSED, handleMissedAlert);

    console.log("[Socket] connecting...");
    socket.connect();

    return () => {
      console.log("[Socket] cleaning up");

      socket.off("connect", handleConnect);
      socket.off("disconnect", handleDisconnect);
      socket.off("connect_error", handleConnectError);

      socket.off(SOCKET_EVENTS.ALERT_NEW, handleNewAlert);
      socket.off(SOCKET_EVENTS.ALERT_UPDATED, handleUpdatedAlert);
      socket.off(SOCKET_EVENTS.ALERT_MISSED, handleMissedAlert);

      socket.disconnect();
    };
  }, [socket, camerasQuery.data, cameraIds, queryClient]);

  const connectionState: SocketConnectionState = !socket
    ? "disconnected"
    : connectionError
      ? "error"
      : isConnected
        ? "connected"
        : "connecting";

  const value = useMemo(
    () => ({
      socket,
      connectionState,
      connectionError,
    }),
    [socket, connectionState, connectionError],
  );

  return (
    <SocketContext.Provider value={value}>
      {children}
    </SocketContext.Provider>
  );
}