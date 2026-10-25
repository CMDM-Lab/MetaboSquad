// Catches and formats API handler responses.
// import { NextRequest } from "next/server";
// import { error } from "@/src/utils/apiResponse";
// import { BUSINESS_STATUS_CODE } from "@/src/config/constants";

// export function withApiHandler(
//   handler: (req: NextRequest) => Promise<Response>,
//   defaultStatus = BUSINESS_STATUS_CODE.ERROR,
// ) {
//   return async (req: NextRequest) => {
//     try {
//       return await handler(req);
//     } catch (err: any) {
//       console.error("API Error:", err);
//       return Response.json(
//         error(err.message || "Internal Server Error", defaultStatus),
//         { status: defaultStatus },
//       );
//     }
//   };
// }
