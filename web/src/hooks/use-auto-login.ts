import authorizationUtil from '@/utils/authorization-util';
import { useEffect, useRef, useState } from 'react';

const AUTO_LOGIN_ENABLED = import.meta.env.VITE_AUTO_LOGIN_ENABLED === 'true';
const DEFAULT_AUTHORIZATION = import.meta.env.VITE_DEFAULT_AUTHORIZATION as
  | string
  | undefined;

export function useAutoLogin() {
  const [isReady, setIsReady] = useState(false);
  const attempted = useRef(false);

  useEffect(() => {
    if (attempted.current) return;
    attempted.current = true;

    if (AUTO_LOGIN_ENABLED && DEFAULT_AUTHORIZATION) {
      const existing = authorizationUtil.getAuthorization();
      if (!existing) {
        authorizationUtil.setItems({
          Authorization: DEFAULT_AUTHORIZATION,
          Token: DEFAULT_AUTHORIZATION,
          userInfo: JSON.stringify({
            name: 'Default User',
            email: 'default@ragflow.local',
            avatar: null,
          }),
        });
      }
    }

    setIsReady(true);
  }, []);

  return { isReady };
}
