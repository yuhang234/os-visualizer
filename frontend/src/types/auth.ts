/** 用户与鉴权类型（设计文档 §11）。 */

export interface UserInfo {
  id: number;
  username: string;
  displayName: string;
  isGuest: boolean;
}

export interface LoginResult {
  accessToken: string;
  tokenType: string;
  expiresIn: number;
  user: UserInfo;
}

export interface HealthInfo {
  status: string;
  app: string;
  /** 相对 `backend/` 的安全标签，后端不下发服务器绝对路径。 */
  dataDirLabel: string;
  modelsDirLabel: string;
  guestDailyChatLimit: number;
}
