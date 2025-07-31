export const handler = async (event) => {
  console.log("EVENT RECEIVED:", JSON.stringify(event));

  // Handle CORS preflight
  if (event.requestContext.http.method === "OPTIONS") {
    return {
      statusCode: 200,
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "OPTIONS,POST"
      },
      body: ''
    };
  }

  let body = {};
  try {
    body = JSON.parse(event.body || '{}');
  } catch (err) {
    console.log("Error parsing body:", err);
    return {
      statusCode: 400,
      headers: {
        "Access-Control-Allow-Origin": "*"
      },
      body: JSON.stringify({ authorized: false, message: "Malformed request body" }),
    };
  }

  const inputKey = body.x_api_key;
  const validKey = process.env.SECRET_API_KEY;

  console.log("Input Key:", inputKey);
  console.log("Valid Key (env):", validKey);

  const authorized = inputKey === validKey;

  return {
    statusCode: authorized ? 200 : 401,
    headers: {
      "Access-Control-Allow-Origin": "*"
    },
    body: JSON.stringify({
      authorized,
      message: authorized ? "Success" : "Invalid API Key"
    })
  };
};